"""Level-wise Apriori mining on the Task 3 author transactions.

Candidate generation and subset pruning are implemented here. Sparse matrix
multiplication counts candidate pairs; higher levels use transaction-ID
intersections. No frequent-pattern mining library is used.
"""

import itertools
import json
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from scipy.sparse import coo_matrix, csc_matrix, csr_matrix

from src.config import EXPERIMENTS_DIR, TABLES_DIR
from src.transactions import AUTHOR_FILE


SUPPORT_LEVELS = ("0.1", "0.5", "1", "2")  # percentages from the assignment


@dataclass
class TransactionIndex:
    n_transactions: int
    n_unique_items: int
    items: list[str]
    singleton_counts: np.ndarray
    pair_counts: csr_matrix
    item_tids: csc_matrix


def minimum_count(n_transactions: int, support_pct: str) -> int:
    return int((Decimal(support_pct) * n_transactions / 100).to_integral_value(rounding=ROUND_CEILING))


def load_index(path: Path = AUTHOR_FILE, lowest_support_pct: str = SUPPORT_LEVELS[0]) -> TransactionIndex:
    """Index only items that can pass the lowest requested support."""
    source = pq.ParquetFile(path)
    n = source.metadata.num_rows
    counts = Counter()
    for batch in source.iter_batches(columns=["venue_ids"]):
        counts.update(batch.column(0).values.to_pylist())

    floor = minimum_count(n, lowest_support_pct)
    items = sorted(item for item, count in counts.items() if count >= floor)
    if not items:
        empty = csr_matrix((n, 0), dtype=np.int32)
        return TransactionIndex(n, len(counts), [], np.array([], dtype=np.int32),
                                csr_matrix((0, 0), dtype=np.int32), empty.tocsc())

    row_chunks, column_chunks = [], []
    offset = 0
    lookup = pa.array(items)
    for batch in source.iter_batches(columns=["venue_ids"]):
        venues = batch.column(0)
        columns = pc.index_in(venues.values, value_set=lookup).fill_null(-1).to_numpy()
        rows = pc.list_parent_indices(venues).to_numpy() + offset
        keep = columns >= 0
        row_chunks.append(rows[keep].astype(np.int32))
        column_chunks.append(columns[keep].astype(np.int32))
        offset += len(venues)

    rows = np.concatenate(row_chunks)
    columns = np.concatenate(column_chunks)
    matrix = coo_matrix((np.ones(len(rows), dtype=np.int32), (rows, columns)),
                        shape=(n, len(items))).tocsr()
    matrix.sum_duplicates()
    if matrix.nnz and np.any(matrix.data != 1):
        raise ValueError("Transaksi berisi venue berulang; item harus unik.")
    singleton_counts = np.asarray(matrix.sum(axis=0)).ravel().astype(np.int32)
    pair_counts = (matrix.T @ matrix).tocsr()
    return TransactionIndex(n, len(counts), items, singleton_counts, pair_counts, matrix.tocsc())


def generate_candidates(previous: set[tuple[int, ...]], size: int) -> set[tuple[int, ...]]:
    """Apriori join and prune: every (k-1)-subset must be frequent."""
    groups = defaultdict(list)
    for itemset in sorted(previous):
        groups[itemset[:-1]].append(itemset[-1])
    candidates = set()
    for prefix, endings in groups.items():
        for left, right in itertools.combinations(endings, 2):
            candidate = prefix + (left, right)
            if len(candidate) == size and all(
                candidate[:i] + candidate[i + 1:] in previous for i in range(size)
            ):
                candidates.add(candidate)
    return candidates


def count_candidate(index: TransactionIndex, candidate: tuple[int, ...]) -> int:
    """Count transactions containing a candidate using sorted posting lists."""
    matrix = index.item_tids
    postings = [matrix.indices[matrix.indptr[i]:matrix.indptr[i + 1]] for i in candidate]
    postings.sort(key=len)
    common = postings[0]
    for next_posting in postings[1:]:
        common = np.intersect1d(common, next_posting, assume_unique=True)
        if len(common) == 0:
            break
    return int(len(common))


def mine(index: TransactionIndex, support_pct: str) -> tuple[dict[tuple[int, ...], int], list[dict]]:
    """Return every frequent itemset and the candidate counts at each level."""
    threshold = minimum_count(index.n_transactions, support_pct)
    frequent = {(i,): int(count) for i, count in enumerate(index.singleton_counts) if count >= threshold}
    levels = [{"size": 1, "n_candidates": index.n_unique_items, "n_frequent": len(frequent)}]
    previous = set(frequent)

    if previous:
        candidates = set(itertools.combinations(sorted(i[0] for i in previous), 2))
        pair_level = {(i, j): int(index.pair_counts[i, j]) for i, j in candidates
                      if index.pair_counts[i, j] >= threshold}
        levels.append({"size": 2, "n_candidates": len(candidates), "n_frequent": len(pair_level)})
        frequent.update(pair_level)
        previous = set(pair_level)

    size = 3
    while previous:
        candidates = generate_candidates(previous, size)
        if not candidates:
            break
        current = {candidate: count for candidate in sorted(candidates)
                   if (count := count_candidate(index, candidate)) >= threshold}
        levels.append({"size": size, "n_candidates": len(candidates), "n_frequent": len(current)})
        frequent.update(current)
        previous = set(current)
        size += 1
    return frequent, levels


def itemsets_frame(index: TransactionIndex, frequent: dict[tuple[int, ...], int]) -> pd.DataFrame:
    rows = [{"itemset": json.dumps([index.items[i] for i in itemset]),
             "size": len(itemset), "support_count": count,
             "support": count / index.n_transactions,
             "support_pct": 100 * count / index.n_transactions}
            for itemset, count in frequent.items()]
    columns = ["itemset", "size", "support_count", "support", "support_pct"]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).sort_values(
        ["support_count", "size", "itemset"], ascending=[False, True, True]
    ).reset_index(drop=True)


def rules_frame(index: TransactionIndex, frequent: dict[tuple[int, ...], int],
                min_confidence: float = 0.5) -> pd.DataFrame:
    """Generate all rules from frequent itemsets, then apply confidence."""
    rows = []
    n = index.n_transactions
    for itemset, joint_count in frequent.items():
        if len(itemset) < 2:
            continue
        for size in range(1, len(itemset)):
            for antecedent in itertools.combinations(itemset, size):
                consequent = tuple(i for i in itemset if i not in antecedent)
                confidence = joint_count / frequent[antecedent]
                if confidence < min_confidence:
                    continue
                support = joint_count / n
                lift = confidence / (frequent[consequent] / n)
                rows.append({
                    "antecedent": json.dumps([index.items[i] for i in antecedent]),
                    "consequent": json.dumps([index.items[i] for i in consequent]),
                    "itemset_size": len(itemset), "support_count": joint_count,
                    "support": support, "support_pct": 100 * support,
                    "confidence": confidence, "confidence_pct": 100 * confidence,
                    "lift": lift,
                })
    columns = ["antecedent", "consequent", "itemset_size", "support_count", "support",
               "support_pct", "confidence", "confidence_pct", "lift"]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows).sort_values(
        ["lift", "support_count", "antecedent", "consequent"],
        ascending=[False, False, True, True],
    ).reset_index(drop=True)


def run_experiments(path: Path = AUTHOR_FILE) -> pd.DataFrame:
    start = time.perf_counter()
    index = load_index(path)
    print(f"Indeks {index.n_transactions:,} transaksi, {index.n_unique_items} item unik; "
          f"{len(index.items)} lolos ambang support terendah "
          f"dibangun dalam {time.perf_counter() - start:.1f} s", flush=True)
    summaries = []
    candidate_rows = []
    for support_pct in SUPPORT_LEVELS:
        started = time.perf_counter()
        frequent, levels = mine(index, support_pct)
        itemsets = itemsets_frame(index, frequent)
        rules = rules_frame(index, frequent)
        label = support_pct.replace(".", "p")
        itemsets.to_csv(EXPERIMENTS_DIR / f"apriori_itemsets_{label}pct.csv", index=False)
        rules.to_csv(EXPERIMENTS_DIR / f"apriori_rules_{label}pct.csv", index=False)
        itemsets.head(10).to_csv(TABLES_DIR / f"apriori_top10_itemsets_{label}pct.csv", index=False)
        for size, name in [(1, "singletons"), (2, "pairs"), (3, "triples")]:
            itemsets[itemsets["size"] == size].head(10).to_csv(
                TABLES_DIR / f"apriori_top10_{name}_{label}pct.csv", index=False)
        rules.head(10).to_csv(TABLES_DIR / f"apriori_top10_lift_{label}pct.csv", index=False)
        rules[(rules["antecedent"].map(json.loads).map(len) == 1) &
              (rules["consequent"].map(json.loads).map(len) == 1)].head(10).to_csv(
            TABLES_DIR / f"apriori_top10_pair_rules_{label}pct.csv", index=False)
        for level in levels:
            candidate_rows.append({"min_support_pct": support_pct, **level})
        summaries.append({
            "min_support_pct": support_pct,
            "min_support_count": minimum_count(index.n_transactions, support_pct),
            "n_transactions": index.n_transactions,
            "n_frequent_itemsets": len(frequent),
            "n_frequent_1": sum(len(k) == 1 for k in frequent),
            "n_frequent_2": sum(len(k) == 2 for k in frequent),
            "n_frequent_3": sum(len(k) == 3 for k in frequent),
            "n_frequent_4plus": sum(len(k) >= 4 for k in frequent),
            "max_itemset_size": max(map(len, frequent), default=0),
            "n_rules_confidence_50pct": len(rules),
            "elapsed_seconds_after_index": round(time.perf_counter() - started, 3),
        })
        print(f"Support {support_pct}%: {len(frequent)} itemset, {len(rules)} rules", flush=True)
    summary = pd.DataFrame(summaries)
    summary.to_csv(TABLES_DIR / "apriori_summary.csv", index=False)
    pd.DataFrame(candidate_rows).to_csv(TABLES_DIR / "apriori_candidates.csv", index=False)
    return summary


if __name__ == "__main__":
    run_experiments()

import csv
import hashlib
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq

from src import preprocess as pp
from src.config import CLEAN_PAPER_AUTHOR, CLEAN_PAPERS, DATA_DIR, TABLES_DIR


def run_pipeline() -> tuple[pa.Table, pp.Funnel]:
    funnel = pp.Funnel()
    table = pp.select_scope(funnel)
    table = pp.handle_missing(table, funnel)
    table, _ = pp.dedupe_authors(table)
    table = pp.remove_duplicates(table, funnel)
    table, _ = pp.normalize_authors(table)
    table, _ = pp.dedupe_authors(table)
    table = pp.apply_venues(table, pp.classify_venues(table))
    table = pp.normalize_year(table, funnel)
    return table, funnel


def paper_table(table: pa.Table) -> pa.Table:
    return pa.table({
        "paper_key": table["key"],
        "title": table["title"],
        "year": table["year"],
        "venue_id": table["venue_id"],
        "venue_name": table["venue_name"],
        "track": table["track"],
        "booktitle": table["booktitle"],
        "n_authors": pc.cast(pc.list_value_length(table["authors"]), pa.int16()),
    })


def paper_author_table(table: pa.Table) -> pa.Table:
    authors = table["authors"].combine_chunks()
    parent = pc.list_parent_indices(authors)
    lengths = pc.list_value_length(authors).to_numpy()
    starts = np.repeat(np.cumsum(lengths) - lengths, lengths)
    position = np.arange(len(starts)) - starts + 1
    return pa.table({
        "paper_key": pc.take(table["key"], parent),
        "author": authors.flatten(),
        "author_pos": pa.array(position, pa.int16()),
        "year": pc.take(table["year"], parent),
        "venue_id": pc.take(table["venue_id"], parent),
    })


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_csv(table: pa.Table, path: Path, batch_size=1_000_000):
    with open(path, "w", encoding="utf-8", newline="") as f:
        for i, batch in enumerate(table.to_batches(batch_size)):
            batch.to_pandas().to_csv(f, index=False, header=i == 0,
                                     quoting=csv.QUOTE_NONNUMERIC, lineterminator="\n")


def export(table: pa.Table) -> pd.DataFrame:
    files = []
    for path, data in [(CLEAN_PAPERS, paper_table(table)), (CLEAN_PAPER_AUTHOR, paper_author_table(table))]:
        pq.write_table(data, path, compression="zstd")
        write_csv(data, path.with_suffix(".csv"))
        for out in (path, path.with_suffix(".csv")):
            files.append({"file": out.name, "n_rows": data.num_rows,
                          "size_mb": round(out.stat().st_size / 2**20, 1), "sha256": sha256(out)})
    manifest = pd.DataFrame(files)
    manifest.to_csv(TABLES_DIR / "dataset_files.csv", index=False)
    lines = [f"{row.sha256}  {row.file}\n" for row in manifest.itertuples()]
    (DATA_DIR / "SHA256SUMS").write_text("".join(lines), encoding="utf-8", newline="\n")
    return manifest


if __name__ == "__main__":
    clean, _ = run_pipeline()
    print(export(clean).to_string(index=False))

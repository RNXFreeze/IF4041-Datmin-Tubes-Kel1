import json
import time
import pandas as pd
import pyarrow.parquet as pq
from pathlib import Path
from typing import Iterable
from collections import Counter
from itertools import combinations
from src.apriori import SUPPORT_LEVELS , minimum_count
from src.config import EXPERIMENTS_DIR , TABLES_DIR
from src.transactions import AUTHOR_FILE

MIN_CONFIDENCE : float = 0.5
ITEMSET_COLUMNS : list[str] = ["itemset" , "size" , "support_count" , "support" , "support_pct"]
RULE_COLUMNS : list[str] = ["antecedent" , "consequent" , "itemset_size" , "support_count" , "support" , "support_pct" , "confidence" , "confidence_pct" , "lift"]

class FPNode :
    __slots__ = ("item" , "count" , "parent" , "children" , "link")

    def __init__(self , item : str | None , count : int , parent : "FPNode | None") -> None :
        self.item = item
        self.count = count
        self.parent = parent
        self.children : dict[str , FPNode] = {}
        self.link : FPNode | None = None

class FPTree :
    def __init__(self , item_count : dict[str , int]) -> None :
        self.root = FPNode(None , 0 , None)
        self.item_count = item_count
        self.order = {item : rank for (rank , item) in (enumerate(sorted(item_count , key = lambda item : (-item_count[item] , item))))}
        self.header : dict[str , FPNode] = {}

    def insert(self , items : list[str] , count : int) -> None :
        node = self.root
        for (item) in (items) :
            child = node.children.get(item)
            if (child is None) :
                child = FPNode(item , count , node)
                node.children[item] = child
                child.link = self.header.get(item)
                self.header[item] = child
            else :
                child.count += count
            node = child

    def is_empty(self) -> bool :
        return len(self.root.children) == 0

    def single_path(self) -> list[FPNode] | None :
        path : list[FPNode] = []
        node = self.root
        while (len(node.children) == 1) :
            node = next(iter(node.children.values()))
            path.append(node)
        return path if (len(node.children) == 0) else None

    def conditional_pattern_base(self , item : str) -> list[tuple[list[str] , int]] :
        base : list[tuple[list[str] , int]] = []
        node = self.header.get(item)
        while (node is not None) :
            path : list[str] = []
            parent = node.parent
            while (parent.item is not None) :
                path.append(parent.item)
                parent = parent.parent
            if (path) :
                base.append((path[:: -1] , node.count))
            node = node.link
        return base

def build_fp_tree(transactions : Iterable[tuple[list[str] , int]] , min_count : int) -> FPTree :
    data = list(transactions)
    item_count : Counter[str] = Counter()
    for (items , count) in (data) :
        for (item) in (set(items)) :
            item_count[item] += count
    tree = FPTree({item : count for (item , count) in (item_count.items()) if (count >= min_count)})
    for (items , count) in (data) :
        frequent_items = sorted({item for (item) in (items) if (item in tree.order)} , key = tree.order.__getitem__)
        if (frequent_items) :
            tree.insert(frequent_items , count)
    return tree

def mine_tree(tree : FPTree , suffix : tuple[str , ...] , min_count : int , patterns : dict[frozenset[str] , int]) -> None :
    path = tree.single_path()
    if (path is not None) :
        for (k) in range (1 , len(path) + 1) :
            for (beta) in (combinations(path , k)) :
                patterns[frozenset(suffix + tuple(node.item for (node) in (beta)))] = min(node.count for (node) in (beta))
        return
    for (item) in (sorted(tree.order , key = tree.order.__getitem__ , reverse = True)) :
        beta = suffix + (item ,)
        patterns[frozenset(beta)] = tree.item_count[item]
        cond_tree = build_fp_tree(tree.conditional_pattern_base(item) , min_count)
        if (not cond_tree.is_empty()) :
            mine_tree(cond_tree , beta , min_count , patterns)

def fp_growth(transactions : list[list[str]] , support_pct : str) -> dict[frozenset[str] , int] :
    min_count = minimum_count(len(transactions) , support_pct)
    tree = build_fp_tree(((transaction , 1) for (transaction) in (transactions)) , min_count)
    patterns : dict[frozenset[str] , int] = {}
    if (not tree.is_empty()) :
        mine_tree(tree , () , min_count , patterns)
    return patterns

def generate_rules(itemsets : dict[frozenset[str] , int] , n_transactions : int , min_confidence : float = MIN_CONFIDENCE) -> pd.DataFrame :
    rows : list[dict] = []
    for (itemset , joint_count) in (itemsets.items()) :
        items = sorted(itemset)
        for (size) in range (1 , len(items)) :
            for (antecedent) in (combinations(items , size)) :
                consequent = [item for (item) in (items) if (item not in antecedent)]
                confidence = joint_count / itemsets[frozenset(antecedent)]
                if (confidence < min_confidence) :
                    continue
                support = joint_count / n_transactions
                rows.append({
                    "antecedent" : json.dumps(list(antecedent)) ,
                    "consequent" : json.dumps(consequent) ,
                    "itemset_size" : len(items) ,
                    "support_count" : joint_count ,
                    "support" : support ,
                    "support_pct" : 100 * support ,
                    "confidence" : confidence ,
                    "confidence_pct" : 100 * confidence ,
                    "lift" : confidence / (itemsets[frozenset(consequent)] / n_transactions) ,
                })
    if (not rows) :
        return pd.DataFrame(columns = RULE_COLUMNS)
    return pd.DataFrame(rows).sort_values(["lift" , "support_count" , "antecedent" , "consequent"] , ascending = [False , False , True , True]).reset_index(drop = True)

def load_transactions(path : Path = AUTHOR_FILE) -> list[list[str]] :
    return pq.read_table(path , columns = ["venue_ids"]).column("venue_ids").to_pylist()

def itemsets_frame(itemsets : dict[frozenset[str] , int] , n_transactions : int) -> pd.DataFrame :
    rows = [{"itemset" : json.dumps(sorted(itemset)) , "size" : len(itemset) , "support_count" : count , "support" : count / n_transactions , "support_pct" : 100 * count / n_transactions} for (itemset , count) in (itemsets.items())]
    if (not rows) :
        return pd.DataFrame(columns = ITEMSET_COLUMNS)
    return pd.DataFrame(rows).sort_values(["support_count" , "size" , "itemset"] , ascending = [False , True , True]).reset_index(drop = True)

def count_by_size(itemsets : dict[frozenset[str] , int]) -> dict[str , int] :
    sizes = Counter(len(itemset) for (itemset) in (itemsets))
    return {"n_frequent_1" : sizes[1] , "n_frequent_2" : sizes[2] , "n_frequent_3" : sizes[3] , "n_frequent_4plus" : sum(count for (size , count) in (sizes.items()) if (size >= 4))}

def is_pair_rule(rules : pd.DataFrame) -> pd.Series :
    return (rules["antecedent"].map(json.loads).map(len) == 1) & (rules["consequent"].map(json.loads).map(len) == 1)

def venue_names() -> dict[str , str] :
    mapping = pd.read_csv(TABLES_DIR / "venue_mapping.csv").drop_duplicates("venue_id")
    return dict(zip(mapping["venue_id"] , mapping["venue_name"]))

def readable(text : str , names : dict[str , str]) -> str :
    return ", ".join(names.get(item , item) for (item) in (json.loads(text)))

def run_experiments(path : Path = AUTHOR_FILE) -> pd.DataFrame :
    transactions = load_transactions(path)
    n = len(transactions)
    summaries : list[dict] = []
    for (support_pct) in (SUPPORT_LEVELS) :
        start = time.perf_counter()
        itemsets = fp_growth(transactions , support_pct)
        elapsed = time.perf_counter() - start
        frame = itemsets_frame(itemsets , n)
        rules = generate_rules(itemsets , n)
        label = support_pct.replace("." , "p")
        frame.to_csv(EXPERIMENTS_DIR / f"fpgrowth_itemsets_{label}pct.csv" , index = False)
        rules.to_csv(EXPERIMENTS_DIR / f"fpgrowth_rules_{label}pct.csv" , index = False)
        frame.head(10).to_csv(TABLES_DIR / f"fpgrowth_top10_itemsets_{label}pct.csv" , index = False)
        for (size , name) in ((1 , "singletons") , (2 , "pairs") , (3 , "triples")) :
            frame[frame["size"] == size].head(10).to_csv(TABLES_DIR / f"fpgrowth_top10_{name}_{label}pct.csv" , index = False)
        rules.head(10).to_csv(TABLES_DIR / f"fpgrowth_top10_lift_{label}pct.csv" , index = False)
        rules[is_pair_rule(rules)].head(10).to_csv(TABLES_DIR / f"fpgrowth_top10_pair_rules_{label}pct.csv" , index = False)
        summaries.append({
            "min_support_pct" : support_pct ,
            "min_support_count" : minimum_count(n , support_pct) ,
            "n_transactions" : n ,
            "n_frequent_itemsets" : len(itemsets) ,
            **count_by_size(itemsets) ,
            "max_itemset_size" : max(map(len , itemsets) , default = 0) ,
            "n_rules_confidence_50pct" : len(rules) ,
            "elapsed_seconds" : round(elapsed , 3) ,
        })
        print(f"Support {support_pct}%: {len(itemsets)} itemset, {len(rules)} rules" , flush = True)
    summary = pd.DataFrame(summaries)
    summary.to_csv(TABLES_DIR / "fpgrowth_summary.csv" , index = False)
    return summary

if (__name__ == "__main__") :
    run_experiments()

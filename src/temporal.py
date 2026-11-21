import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq
from pathlib import Path
from src.config import EXPERIMENTS_DIR , TABLES_DIR
from src.fp_growth import count_by_size , fp_growth , generate_rules , itemsets_frame , load_transactions
from src.transactions import AUTHOR_FILE , AUTHOR_YEAR_FILE

PERIODS : dict[str , tuple[int , int]] = {
    "2015-2017" : (2015 , 2017) ,
    "2018-2020" : (2018 , 2020) ,
    "2021-2023" : (2021 , 2023) ,
    "2024-2025" : (2024 , 2025) ,
}
TEMPORAL_SUPPORT : str = "0.1"
TEMPORAL_MIN_CONFIDENCE : float = 0.5

def load_period_transactions(path : Path = AUTHOR_YEAR_FILE) -> dict[str , list[list[str]]] :
    table = pq.read_table(path , columns = ["year" , "venue_ids"])
    result : dict[str , list[list[str]]] = {}
    for (name , (start , end)) in (PERIODS.items()) :
        mask = pc.and_(pc.greater_equal(table["year"] , start) , pc.less_equal(table["year"] , end))
        result[name] = table.filter(mask).column("venue_ids").to_pylist()
    return result

def mine_periods(period_transactions : dict[str , list[list[str]]] , support_pct : str = TEMPORAL_SUPPORT , min_confidence : float = TEMPORAL_MIN_CONFIDENCE) -> dict[str , dict] :
    results : dict[str , dict] = {}
    for (name , transactions) in (period_transactions.items()) :
        itemsets = fp_growth(transactions , support_pct)
        rules = generate_rules(itemsets , len(transactions) , min_confidence)
        results[name] = {"n_transactions" : len(transactions) , "itemsets" : itemsets , "rules" : rules}
        print(f"[{name}] {len(transactions) :,} transaksi -> {len(itemsets)} itemset, {len(rules)} rules" , flush = True)
    return results

def period_summary(results : dict[str , dict]) -> pd.DataFrame :
    return pd.DataFrame([{"period" : name , "n_transactions" : result["n_transactions"] , "n_frequent_itemsets" : len(result["itemsets"]) , **count_by_size(result["itemsets"]) , "n_rules" : len(result["rules"])} for (name , result) in (results.items())])

def classify_presence(presence : list[bool]) -> str :
    if (all(presence)) :
        return "Bertahan"
    first = presence.index(True)
    last = len(presence) - 1 - presence[:: -1].index(True)
    if ((not presence[0]) and all(presence[first :])) :
        return "Muncul"
    if ((not presence[-1]) and all(presence[: last + 1])) :
        return "Menghilang"
    return "Fluktuatif"

def compare_rules_across_periods(results : dict[str , dict]) -> pd.DataFrame :
    periods = list(results)
    frames = [result["rules"][["antecedent" , "consequent" , "lift"]].assign(period = name) for (name , result) in (results.items()) if (not result["rules"].empty)]
    if (not frames) :
        return pd.DataFrame(columns = ["antecedent" , "consequent" , *periods , "n_periods" , "status" , "delta"])
    pivot = pd.concat(frames).pivot_table(index = ["antecedent" , "consequent"] , columns = "period" , values = "lift" , aggfunc = "first").reindex(columns = periods).reset_index()
    pivot.columns.name = None
    presence = pivot[periods].notna()
    pivot["n_periods"] = presence.sum(axis = 1)
    pivot["status"] = [classify_presence(list(row)) for (row) in (presence.itertuples(index = False))]
    pivot["delta"] = pivot[periods].ffill(axis = 1).iloc[: , -1] - pivot[periods].bfill(axis = 1).iloc[: , 0]
    return pivot.sort_values(["n_periods" , periods[-1] , "antecedent" , "consequent"] , ascending = [False , False , True , True] , na_position = "last" , ignore_index = True)

def venue_support_trend(period_transactions : dict[str , list[list[str]]] , venues : list[str]) -> pd.DataFrame :
    rows : dict[str , dict[str , float]] = {}
    for (name , transactions) in (period_transactions.items()) :
        counts = dict.fromkeys(venues , 0)
        for (transaction) in (transactions) :
            for (venue) in (transaction) :
                if (venue in counts) :
                    counts[venue] += 1
        rows[name] = {venue : 100 * count / len(transactions) for (venue , count) in (counts.items())}
    return pd.DataFrame(rows).rename_axis("venue_id")

def compare_representations(support_pct : str = TEMPORAL_SUPPORT , min_confidence : float = TEMPORAL_MIN_CONFIDENCE) -> dict[str , dict] :
    return mine_periods({"Author-Based" : load_transactions(AUTHOR_FILE) , "Author-Year-Based" : load_transactions(AUTHOR_YEAR_FILE)} , support_pct , min_confidence)

def run_temporal() -> tuple[dict[str , list[list[str]]] , dict[str , dict]] :
    period_tx = load_period_transactions()
    results = mine_periods(period_tx)
    for (name , result) in (results.items()) :
        itemsets_frame(result["itemsets"] , result["n_transactions"]).to_csv(EXPERIMENTS_DIR / f"temporal_itemsets_{name}.csv" , index = False)
        result["rules"].to_csv(EXPERIMENTS_DIR / f"temporal_rules_{name}.csv" , index = False)
    period_summary(results).to_csv(TABLES_DIR / "temporal_summary.csv" , index = False)
    compare_rules_across_periods(results).to_csv(TABLES_DIR / "temporal_rule_comparison.csv" , index = False)
    return period_tx , results

if (__name__ == "__main__") :
    run_temporal()

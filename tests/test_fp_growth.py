import random
import tempfile
import unittest
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from itertools import combinations
from src.apriori import itemsets_frame as apriori_itemsets_frame
from src.apriori import load_index , mine , rules_frame
from src.fp_growth import count_by_size , fp_growth , generate_rules , itemsets_frame , load_transactions
from src.temporal import classify_presence , compare_rules_across_periods , load_period_transactions , mine_periods

def write_transactions(transactions : list[list[str]] , path : Path , years : list[int] | None = None) -> None :
    columns = {"author" : pa.array([f"a{i}" for (i) in range (len(transactions))])}
    if (years is not None) :
        columns["year"] = pa.array(years , type = pa.int16())
    columns["venue_ids"] = pa.array([sorted(set(transaction)) for (transaction) in (transactions)] , type = pa.list_(pa.string()))
    pq.write_table(pa.table(columns) , path)

def brute_force(transactions : list[list[str]] , min_count : int) -> dict[frozenset[str] , int] :
    sets = [set(transaction) for (transaction) in (transactions)]
    items = sorted(set().union(*sets))
    result : dict[frozenset[str] , int] = {}
    for (k) in range (1 , len(items) + 1) :
        for (combo) in (combinations(items , k)) :
            count = sum(1 for (transaction) in (sets) if (transaction.issuperset(combo)))
            if (count >= min_count) :
                result[frozenset(combo)] = count
    return result

def random_database(rng : random.Random) -> list[list[str]] :
    items = [f"v{i}" for (i) in range (rng.randint(3 , 8))]
    return [rng.sample(items , rng.randint(1 , len(items))) for (_) in range (rng.randint(5 , 40))]

class TestFPGrowth(unittest.TestCase) :
    def test_textbook_example(self) -> None :
        transactions = [["I1" , "I2" , "I5"] , ["I2" , "I4"] , ["I2" , "I3"] , ["I1" , "I2" , "I4"] , ["I1" , "I3"] , ["I2" , "I3"] , ["I1" , "I3"] , ["I1" , "I2" , "I3" , "I5"] , ["I1" , "I2" , "I3"]]
        result = fp_growth(transactions , "20")
        self.assertEqual(len(result) , 13)
        self.assertEqual(result[frozenset({"I1" , "I2" , "I3"})] , 2)
        self.assertEqual(result[frozenset({"I1" , "I2" , "I5"})] , 2)

    def test_slide_example(self) -> None :
        result = fp_growth([list("facdgimp") , list("abcflmo") , list("bfhjow") , list("bcksp") , list("afcelpmn")] , "60")
        self.assertEqual(count_by_size(result) , {"n_frequent_1" : 6 , "n_frequent_2" : 7 , "n_frequent_3" : 4 , "n_frequent_4plus" : 1})

    def test_random_against_brute_force(self) -> None :
        rng = random.Random(2026)
        for (_) in range (50) :
            transactions = random_database(rng)
            for (support_pct) in ("10" , "30" , "50") :
                min_count = -(-int(support_pct) * len(transactions) // 100)
                self.assertEqual(fp_growth(transactions , support_pct) , brute_force(transactions , min_count))

    def test_same_as_group_apriori(self) -> None :
        rng = random.Random(7)
        with tempfile.TemporaryDirectory() as folder :
            for (trial) in range (10) :
                path = Path(folder) / f"db_{trial}.parquet"
                write_transactions(random_database(rng) , path)
                transactions = load_transactions(path)
                for (support_pct) in ("10" , "30") :
                    index = load_index(path , support_pct)
                    frequent , _ = mine(index , support_pct)
                    itemsets = fp_growth(transactions , support_pct)
                    pd.testing.assert_frame_equal(itemsets_frame(itemsets , len(transactions)) , apriori_itemsets_frame(index , frequent) , check_dtype = False)
                    pd.testing.assert_frame_equal(generate_rules(itemsets , len(transactions)) , rules_frame(index , frequent) , check_dtype = False)

class TestTemporal(unittest.TestCase) :
    def test_load_period_transactions(self) -> None :
        with tempfile.TemporaryDirectory() as folder :
            path = Path(folder) / "author_year.parquet"
            write_transactions([["a"] , ["b"] , ["c"] , ["d"] , ["e"] , ["f"]] , path , years = [2015 , 2017 , 2018 , 2023 , 2024 , 2025])
            sizes = {name : len(transactions) for (name , transactions) in (load_period_transactions(path).items())}
        self.assertEqual(sizes , {"2015-2017" : 2 , "2018-2020" : 1 , "2021-2023" : 1 , "2024-2025" : 2})

    def test_classify_presence(self) -> None :
        self.assertEqual(classify_presence([True , True , True , True]) , "Bertahan")
        self.assertEqual(classify_presence([False , False , True , True]) , "Muncul")
        self.assertEqual(classify_presence([True , True , False , False]) , "Menghilang")
        self.assertEqual(classify_presence([True , False , True , False]) , "Fluktuatif")

    def test_compare_rules_across_periods(self) -> None :
        early = [["a" , "b"]] * 6 + [["c"]] * 4
        late = [["a" , "b"]] * 3 + [["c" , "d"]] * 5 + [["a"]] * 2
        comparison = compare_rules_across_periods(mine_periods({"P1" : early , "P2" : late} , "30" , 0.5)).set_index(["antecedent" , "consequent"])
        self.assertEqual(comparison.loc[('["a"]' , '["b"]') , "status"] , "Bertahan")
        self.assertEqual(comparison.loc[('["c"]' , '["d"]') , "status"] , "Muncul")
        self.assertAlmostEqual(comparison.loc[('["b"]' , '["a"]') , "P1"] , 1.0 / 0.6)

if (__name__ == "__main__") :
    unittest.main()

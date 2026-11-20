"""Small exact example covering candidate pruning and rule metrics."""

import tempfile
import unittest
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from src.apriori import generate_candidates, load_index, mine, minimum_count, rules_frame


class AprioriTest(unittest.TestCase):
    def test_levelwise_counts_and_rules(self):
        transactions = [["a", "b", "c"], ["a", "b"], ["a", "c"], ["b", "c"], ["a", "b", "c"]]
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "transactions.parquet"
            pq.write_table(pa.table({"venue_ids": pa.array(transactions, type=pa.list_(pa.string()))}), path)
            index = load_index(path, "20")

        self.assertEqual(index.items, ["a", "b", "c"])
        self.assertEqual(minimum_count(5, "40"), 2)
        frequent, levels = mine(index, "40")
        self.assertEqual(frequent, {
            (0,): 4, (1,): 4, (2,): 4,
            (0, 1): 3, (0, 2): 3, (1, 2): 3,
            (0, 1, 2): 2,
        })
        self.assertEqual([level["n_frequent"] for level in levels], [3, 3, 1])
        rules = rules_frame(index, frequent)
        rule = rules[(rules["antecedent"] == '["a", "b"]') &
                     (rules["consequent"] == '["c"]')].iloc[0]
        self.assertAlmostEqual(rule["support"], 2 / 5)
        self.assertAlmostEqual(rule["confidence"], 2 / 3)
        self.assertAlmostEqual(rule["lift"], (2 / 3) / (4 / 5))

        frequent_60, _ = mine(index, "60")
        self.assertEqual(len(frequent_60), 6)
        frequent_80, _ = mine(index, "80")
        self.assertEqual(len(frequent_80), 3)

    def test_candidate_pruning(self):
        self.assertEqual(generate_candidates({(0, 1), (0, 2), (1, 2)}, 3), {(0, 1, 2)})
        self.assertEqual(generate_candidates({(0, 1), (0, 2)}, 3), set())


if __name__ == "__main__":
    unittest.main()

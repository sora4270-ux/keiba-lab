import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_nar_pick_marks import evaluate


class MarkAuditTest(unittest.TestCase):
    def test_rank_hit_rates(self):
        data = {"races": [{"ranking": [{"no": n} for n in [4, 2, 3, 1, 5]],
                           "result": [2, 4, 3]},
                          {"ranking": [{"no": n} for n in [4, 2, 3, 1, 5]],
                           "result": [1, 3, 2]}]}
        report = evaluate(data)
        self.assertEqual(report["settled_with_valid_result"], 2)
        self.assertEqual(report["by_rank_mark"][0]["wins"], 0)
        self.assertEqual(report["by_rank_mark"][0]["top3"], 1)
        self.assertEqual(report["by_rank_mark"][1]["wins"], 1)
        self.assertEqual(report["by_rank_mark"][1]["top3"], 2)
        self.assertIsNone(report["roi_percent"])

    def test_unsettled_skipped(self):
        report = evaluate({"races": [{"ranking": [{"no": 1}], "result": None}]})
        self.assertEqual(report["settled_with_valid_result"], 0)
        self.assertIsNone(report["by_rank_mark"][0]["win_rate_percent"])

    def test_duplicate_ranking_excluded(self):
        report = evaluate({"races": [{"ranking": [{"no": 2}, {"no": 2}],
                                      "result": [2, 3, 4]}]})
        self.assertEqual(report["settled_with_valid_result"], 0)
        self.assertEqual(report["skipped_unsettled_or_invalid"], 1)

    def test_invalid_podium_excluded(self):
        report = evaluate({"races": [{"ranking": [{"no": 2}],
                                      "result": [0, 3, 4]}]})
        self.assertEqual(report["settled_with_valid_result"], 0)

    def test_dead_heat_alternatives_excluded(self):
        report = evaluate({"races": [{"ranking": [{"no": 2}],
                                      "result": [2, 3, 4],
                                      "result_alternatives": [[2, 3, 4], [3, 2, 4]]}]})
        self.assertEqual(report["settled_with_valid_result"], 0)

    def test_single_consistent_alternative_allowed(self):
        report = evaluate({"races": [{"ranking": [{"no": 2}],
                                      "result": [2, 3, 4],
                                      "result_alternatives": [[2, 3, 4]]}]})
        self.assertEqual(report["settled_with_valid_result"], 1)

    def test_invalid_schema(self):
        with self.assertRaises(ValueError):
            evaluate({"races": None})


if __name__ == "__main__":
    unittest.main()

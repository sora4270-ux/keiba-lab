import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_nar_roi_coverage import coverage


def payback():
    row = [""] * 6
    row[0], row[1], row[2], row[4], row[5] = "大井", "20261001", "1", "3", "240"
    return {"payback": [(row, {})]}


def record(with_odds=True):
    r = {"id": "nar-20261001-大井-01",
         "locked_at": "2026-10-01T11:50:00+09:00",
         "cutoff_at": "2026-10-01T12:00:00+09:00",
         "ranking": [{"no": 3}]}
    if with_odds:
        r["market_at_lock"] = {"updated_at": "2026-10-01T11:49:00+09:00",
                               "horses": [{"no": 3, "odds": 2.4}]}
    return r


class CoverageTests(unittest.TestCase):
    def test_both_sources_present_is_not_roi(self):
        result = coverage({"races": [record()]}, payback(), "2026-10")
        self.assertEqual(result["both_present"], 1)
        self.assertEqual(result["coverage_percent"], 100.0)
        self.assertIsNone(result["roi_percent"])

    def test_missing_prelock_odds_not_counted(self):
        result = coverage({"races": [record(with_odds=False)]}, payback(), "2026-10")
        self.assertEqual(result["both_present"], 0)
        self.assertEqual(result["frozen_forecasts_checked"], 1)

    def test_missing_payout_not_loss(self):
        result = coverage({"races": [record()]}, {"payback": []}, "2026-10")
        self.assertEqual(result["both_present"], 0)
        self.assertEqual(result["by_status"]["official_payout_unavailable"], 1)

    def test_month_scoped(self):
        result = coverage({"races": [record()]}, payback(), "2026-09")
        self.assertEqual(result["frozen_forecasts_checked"], 0)
        self.assertIsNone(result["coverage_percent"])


if __name__ == "__main__":
    unittest.main()

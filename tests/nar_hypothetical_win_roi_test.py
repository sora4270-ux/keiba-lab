import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_nar_hypothetical_win_roi import simulate


class WinSimulationTests(unittest.TestCase):
    @patch("audit_nar_hypothetical_win_roi.extract")
    @patch("audit_nar_hypothetical_win_roi.audit")
    def test_payout_and_exclusion(self, audit, extract):
        audit.return_value = [
            {"race_id": "nar-20261120-A-01", "horse_no": "3",
             "audit_status": "timestamp_checks_passed_not_authenticated"},
            {"race_id": "nar-20261120-A-02", "horse_no": "4",
             "audit_status": "timestamp_checks_passed_not_authenticated"},
            {"race_id": "nar-20261120-A-03", "horse_no": "5",
             "audit_status": "missing_or_invalid_timestamps"}]
        extract.return_value = ([
            {"race_id": "nar-20261120-A-01", "horse_no": "3",
             "official_payout_per_100_yen": "450", "official_result_verified": "true"},
            {"race_id": "nar-20261120-A-02", "horse_no": "4",
             "official_payout_per_100_yen": "0", "official_result_verified": "true"}], {})
        report = simulate({"races": []}, {}, "2026-11")
        self.assertEqual(report["eligible_races"], 2)
        self.assertEqual(report["hypothetical_stake_yen"], 200)
        self.assertEqual(report["official_payout_sum_yen"], 450)
        self.assertEqual(report["hypothetical_return_rate_percent"], 225)
        self.assertEqual(report["excluded"]["prelock_missing_or_invalid_timestamps"], 1)

    @patch("audit_nar_hypothetical_win_roi.extract", return_value=([], {}))
    @patch("audit_nar_hypothetical_win_roi.audit", return_value=[])
    def test_empty_has_no_rate(self, audit, extract):
        report = simulate({"races": []}, {}, "2026-11")
        self.assertIsNone(report["hypothetical_return_rate_percent"])


if __name__ == "__main__":
    unittest.main()

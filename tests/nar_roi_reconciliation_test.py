import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from reconcile_nar_roi import reconcile


def prediction(**kwargs):
    data = {"race_id": "20261001-1-1", "horse_no": "3", "grade": "S",
            "bet_type": "win", "stake_yen": "100",
            "decision_time": "2026-10-01T12:00:00+09:00",
            "odds_observed_time": "2026-10-01T11:59:00+09:00", "odds": "2.4"}
    data.update(kwargs)
    return data


def payout(**kwargs):
    data = {"race_id": "20261001-1-1", "horse_no": "3", "bet_type": "win",
            "official_payout_per_100_yen": "240", "official_result_verified": "true"}
    data.update(kwargs)
    return data


class ReconciliationTests(unittest.TestCase):
    def test_matched_winner_and_loser(self):
        result = reconcile([prediction(), prediction(race_id="other")],
                           [payout(), payout(race_id="other",
                                             official_payout_per_100_yen="0")])
        self.assertEqual(result["accepted"], 2)
        self.assertEqual(result["by_grade"]["S"]["win"]["roi_percent"], "120.00")

    def test_missing_is_not_a_loss(self):
        result = reconcile([prediction()], [])
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["reconciliation"]["excluded"]["missing_payout"], 1)
        self.assertIsNone(result["by_grade"]["S"]["win"]["roi_percent"])

    def test_ambiguous_and_unverified_are_excluded(self):
        result = reconcile([prediction(), prediction(race_id="other")],
                           [payout(), payout(), payout(race_id="other",
                                official_result_verified="false")])
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["reconciliation"]["excluded"]["ambiguous_payout"], 1)
        self.assertEqual(result["reconciliation"]["excluded"]["unverified_payout"], 1)

    def test_future_odds_still_rejected(self):
        result = reconcile([prediction(odds_observed_time="2026-10-01T12:01:00+09:00")],
                           [payout()])
        self.assertEqual(result["accepted"], 0)
        self.assertEqual(result["rejected"]["future_odds"], 1)


if __name__ == "__main__":
    unittest.main()

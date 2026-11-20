import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from evaluate_nar_roi import evaluate


def bet(**changes):
    row = {"race_id": "20261001-1-1", "horse_no": "3", "grade": "S",
           "bet_type": "win", "stake_yen": "100",
           "official_payout_per_100_yen": "240",
           "decision_time": "2026-10-01T12:00:00+09:00",
           "odds_observed_time": "2026-10-01T11:59:00+09:00",
           "odds": "2.4", "official_result_verified": "true"}
    row.update(changes)
    return row


class RoiTests(unittest.TestCase):
    def test_verified_win_and_loss(self):
        result = evaluate([bet(), bet(race_id="20261001-1-2",
                                       official_payout_per_100_yen="0")])
        self.assertEqual(result["by_grade"]["S"]["win"]["roi_percent"], "120.00")
        self.assertEqual(result["accepted"], 2)

    def test_future_odds_unverified_and_duplicates_rejected(self):
        result = evaluate([bet(), bet(), bet(race_id="other", official_result_verified="false"),
                           bet(race_id="future", odds_observed_time="2026-10-01T12:01:00+09:00")])
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(result["rejected"]["duplicate_bet"], 1)
        self.assertEqual(result["rejected"]["unverified_payout"], 1)
        self.assertEqual(result["rejected"]["future_odds"], 1)

    def test_empty_is_not_zero_roi(self):
        result = evaluate([])
        self.assertIsNone(result["by_grade"]["S"]["place"]["roi_percent"])


if __name__ == "__main__":
    unittest.main()

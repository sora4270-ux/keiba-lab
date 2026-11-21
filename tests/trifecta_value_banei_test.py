import datetime as dt
import sys
import unittest
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from update_nar import trifecta_value_shadow, is_banei_venue, forecast


class TrifectaValueAndBaneiTest(unittest.TestCase):
    def setUp(self):
        self.now = dt.datetime(2026, 11, 21, 12, 0, tzinfo=ZoneInfo("Asia/Tokyo"))
        self.ordered = [(0.05, (1, 2, 3)), (0.01, (2, 1, 3))]

    def test_missing_market_is_skip(self):
        self.assertEqual(trifecta_value_shadow(self.ordered, None, self.now)["status"], "skip")

    def test_stale_market_is_skip(self):
        old = (self.now - dt.timedelta(minutes=20)).isoformat()
        plan = trifecta_value_shadow(self.ordered, {(1, 2, 3): 40}, self.now, old)
        self.assertEqual(plan["reason"], "official_trifecta_odds_stale")

    def test_margin_and_budget(self):
        quotes = {(1, 2, 3): 30, (2, 1, 3): 60}
        plan = trifecta_value_shadow(self.ordered, quotes, self.now, self.now.isoformat())
        self.assertEqual(plan["tickets"], [[1, 2, 3]])
        self.assertEqual(plan["stake_yen"], 100)
        self.assertEqual(plan["status"], "candidate")

    def test_no_margin_skip(self):
        plan = trifecta_value_shadow(self.ordered, {(1, 2, 3): 10}, self.now, self.now.isoformat())
        self.assertEqual(plan["status"], "skip")

    def test_shadow_is_explicitly_non_purchase(self):
        horses = [
            {"no": i, "name": str(i), "overall": (1, 10),
             "distance": (1, 10), "venue": (1, 10), "jockey": (1, 10)}
            for i in range(1, 7)
        ]
        race = {"id": "test-safe", "date": "2026-11-21", "venue": "佐賀",
                "race_no": 1, "name": "test", "horses": horses,
                "start": self.now + dt.timedelta(hours=1)}
        result = forecast(race, self.now)
        self.assertEqual(result["trifecta_purchase_decision"]["action"], "skip")
        self.assertTrue(result["trifecta_purchase_decision"]["production_tickets_unchanged"])
        self.assertEqual(result["feature_validation"]["coverage_counts"]["carried_weight"], 0)
        self.assertEqual(result["feature_validation"]["coverage_counts"]["running_style"], 0)

    def test_banei_detection(self):
        self.assertTrue(is_banei_venue("帯広"))
        self.assertTrue(is_banei_venue("ばんえい十勝"))
        self.assertFalse(is_banei_venue("佐賀"))

    def test_banei_forecast_is_explicitly_provisional(self):
        horses = [
            {"no": i, "name": str(i), "overall": (1, 10),
             "distance": (1, 10), "venue": (1, 10), "jockey": (1, 10)}
            for i in range(1, 7)
        ]
        race = {"id": "test-banei", "date": "2026-11-21", "venue": "帯広",
                "race_no": 1, "name": "test", "horses": horses,
                "start": self.now + dt.timedelta(hours=1)}
        result = forecast(race, self.now, market={i: {"odds": float(i + 1)} for i in range(1, 7)})
        self.assertEqual(result["model"], "banei_market_only_provisional_v1")
        self.assertFalse(result["banei_validation"]["dedicated_model_validated"])
        self.assertEqual(result["ranking"][0]["no"], 1)


if __name__ == "__main__":
    unittest.main()

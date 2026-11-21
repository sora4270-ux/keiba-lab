import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_nar_ev_staking_shadow import evaluate,report

class EVShadowTest(unittest.TestCase):
    def setUp(self):
        self.r={"id":"test","start_at":"2026-11-20T13:00:00+09:00",
                "cutoff_at":"2026-11-20T12:45:00+09:00","locked_at":"2026-11-20T12:40:00+09:00",
                "ranking":[{"no":1,"win_probability":.4}],
                "market_at_lock":{"updated_at":"2026-11-20T12:38:00+09:00",
                                  "horses":[{"no":1,"odds":4.0}]}}
    def test_positive_shadow_capped(self):
        r=evaluate(self.r)
        self.assertEqual(r["status"],"shadow_candidate")
        self.assertEqual(r["shadow_fixed_yen"],100)
        self.assertEqual(r["shadow_fractional_kelly_yen"],300)
        self.assertFalse(r["live_wager_allowed"])
    def test_low_edge_skips(self):
        self.r["market_at_lock"]["horses"][0]["odds"]=2.0
        self.assertEqual(evaluate(self.r)["reason"],"below_edge_threshold")
    def test_future_odds_skips(self):
        self.r["market_at_lock"]["updated_at"]="2026-11-20T12:46:00+09:00"
        self.assertEqual(evaluate(self.r)["reason"],"invalid_cutoff")
    def test_stale_skips(self):
        self.r["market_at_lock"]["updated_at"]="2026-11-20T12:20:00+09:00"
        self.assertEqual(evaluate(self.r)["reason"],"stale_odds")
    def test_missing_odds_skips(self):
        self.r["market_at_lock"]={}
        self.assertEqual(evaluate(self.r)["reason"],"market_missing_or_malformed")
    def test_invalid_probability_skips(self):
        self.r["ranking"][0]["win_probability"]=float("nan")
        self.assertEqual(evaluate(self.r)["reason"],"invalid_probability")
    def test_report_never_allows_real_bet(self):
        rows=report([self.r])
        self.assertEqual(rows["shadow_candidates"],1)
        self.assertTrue(all(not x["live_wager_allowed"] for x in rows["rows"]))
if __name__=="__main__":
    unittest.main()

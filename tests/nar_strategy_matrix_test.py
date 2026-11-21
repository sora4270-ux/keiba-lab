import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_nar_strategy_matrix import tickets, frozen_odds, METHODS

class StrategyMatrixTests(unittest.TestCase):
    def setUp(self):
        self.r={"ranking":[{"no":1,"win_probability":.5},{"no":2,"win_probability":.3},{"no":3,"win_probability":.2},{"no":4},{"no":5},{"no":6}],
                "venue":"大井","locked_at":"2026-11-20T12:40:00+09:00",
                "cutoff_at":"2026-11-20T12:45:00+09:00",
                "market_at_lock":{"updated_at":"2026-11-20T12:35:00+09:00","horses":[{"no":1,"odds":3.0}]},
                "trio_tickets":[[1,2,3]],"tickets":[[1,2,3]]}
        self.info={"wide":{(1,2):250,(1,3):300,(2,3):400},
                   "payout":{"win":300,"trio":500,"trifecta":1000},
                   "winning":{"win":(1,),"trio":(1,2,3),"trifecta":(1,2,3)}}
    def test_all_methods_have_valid_nonnegative_stake(self):
        for m in METHODS:
            with self.subTest(m=m):
                spent,paid,_=tickets(self.r,self.info,"S",m)
                self.assertGreaterEqual(spent,0)
                self.assertEqual(spent%100,0)
                self.assertGreaterEqual(paid,0)
    def test_value_filter(self):
        self.assertEqual(tickets(self.r,self.info,"S","win_value_130")[:2],(100,300))
        self.assertEqual(tickets(self.r,self.info,"S","win_value_110")[:2],(100,300))
    def test_missing_odds_skips_value(self):
        self.r["market_at_lock"]={}
        self.assertIsNone(frozen_odds(self.r))
        self.assertEqual(tickets(self.r,self.info,"S","win_value_110")[0],0)
    def test_future_market_skips_value(self):
        self.r["market_at_lock"]["updated_at"]="2026-11-20T12:50:00+09:00"
        self.assertEqual(tickets(self.r,self.info,"S","win_value_110")[0],0)
    def test_banei_skipped(self):
        self.r["venue"]="帯広"
        self.assertEqual(tickets(self.r,self.info,"S","wide_top3_flat")[0],0)
    def test_top3_three_tickets(self):
        self.assertEqual(tickets(self.r,self.info,"S","wide_top3")[:2],(300,950))
    def test_trifecta_settlement(self):
        self.assertEqual(tickets(self.r,self.info,"S","trifecta_frozen_first")[:2],(100,1000))
if __name__=="__main__":
    unittest.main()

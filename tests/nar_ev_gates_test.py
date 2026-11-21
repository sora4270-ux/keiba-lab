import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_nar_ev_gates import assess

class GateTests(unittest.TestCase):
    def test_empty_blocks(self):
        result=assess({}, {})
        self.assertFalse(result["gates_passed"])
        self.assertIn("no_records",result["blocking_reasons"])
    def test_coverage_holdout_and_calibration_blocks(self):
        readiness={"counts":{"total_records":100,"fresh_top_odds":79},
                   "all":{"bins":[{"races":100}]},
                   "later_dates":{"races":25,"bins":[{"races":25,"actual_win_percent":40,"mean_predicted_percent":30}]},
                   "holdout_days":5}
        result=assess(readiness,{"shadow_candidates":0})
        for reason in ("odds_coverage_below_target","insufficient_temporal_holdout",
                       "sparse_holdout_probability_bins","holdout_probability_miscalibration",
                       "no_positive_ev_candidates"):
            self.assertIn(reason,result["blocking_reasons"])
    def test_even_perfect_looking_history_never_unlocks_bets(self):
        r={"counts":{"total_records":500,"fresh_top_odds":500},
           "all":{"bins":[{"races":500}]},
           "later_dates":{"races":350,"bins":[{"races":350,"actual_win_percent":40,"mean_predicted_percent":40}]},
           "holdout_days":20}
        result=assess(r,{"shadow_candidates":100})
        self.assertFalse(result["gates_passed"])
        self.assertIn("independent_prelock_capture_not_authenticated",result["blocking_reasons"])
if __name__=="__main__":
    unittest.main()

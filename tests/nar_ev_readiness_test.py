import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_nar_ev_readiness import analyze

class EVReadinessTests(unittest.TestCase):
    def test_invalid_records_and_empty_calibration(self):
        report=analyze([{},{"ranking":[{"no":1,"win_probability":.4}],"market_at_lock":{}}],{"payback":[]})
        self.assertEqual(report["counts"]["ranking_missing"],1)
        self.assertEqual(report["counts"]["odds_market_missing_or_malformed"],1)
        self.assertEqual(report["all"]["races"],0)
        self.assertEqual(report["holdout_days"],0)
    def test_probability_rejected(self):
        r={"ranking":[{"no":1,"win_probability":float("nan")}]}
        self.assertEqual(analyze([r],{"payback":[]})["counts"]["probability_invalid"],1)
if __name__=="__main__":
    unittest.main()

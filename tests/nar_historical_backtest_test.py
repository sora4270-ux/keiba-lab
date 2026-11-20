import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backtest_nar_features import backtest, valid_record

def record(date="2026-11-19",winner=1):
    return {"date":date,"start_at":date+"T12:00:00+09:00",
      "predicted_at":date+"T11:40:00+09:00","locked_at":date+"T11:44:00+09:00",
      "cutoff_at":date+"T11:45:00+09:00",
      "ranking":[{"no":1},{"no":2},{"no":3}],
      "feature_validation":{"top_no":2},"result":[winner,3,2] if winner==1 else [2,3,1]}

class BacktestTests(unittest.TestCase):
    def test_paired_accuracy(self):
        report=backtest([record(),record("2026-11-20",2)])
        self.assertEqual(report["eligible"],2)
        self.assertEqual(report["model"]["win_rate"],50)
        self.assertEqual(report["observed_features"]["win_rate"],50)
        self.assertEqual(report["model"]["top3_rate"],100)

    def test_excludes_late_and_draft_and_missing_shadow(self):
        late=record()
        late["locked_at"]="2026-11-19T11:46:00+09:00"
        draft=record()
        draft["status"]="draft"
        missing=record()
        missing["feature_validation"]={}
        self.assertEqual(backtest([late,draft,missing])["eligible"],0)
        self.assertEqual(backtest([late,draft,missing])["skipped"],3)

    def test_no_result_reconstruction(self):
        item=record()
        item["result"]=None
        self.assertFalse(valid_record(item))

if __name__=="__main__":
    unittest.main()

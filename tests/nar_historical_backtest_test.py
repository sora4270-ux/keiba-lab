import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from backtest_nar_features import backtest, valid_record

def record(date="2026-11-19",winner=1):
    return {"id":"nar-"+date+"-test","venue":"test","date":date,"start_at":date+"T12:00:00+09:00",
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

    def test_surprise_result_stays_in_denominator(self):
        r=record()
        r["result"]=[9,8,3]
        x=backtest([r])
        self.assertEqual(x["eligible"],1)
        self.assertEqual(x["unranked_podium_races"],1)
        self.assertEqual(x["model"]["win_rate"],0)
        self.assertEqual(x["observed_features"]["top3_rate"],0)
    def test_strict_cutoff_and_duplicate_conflict(self):
        a=record()
        late=dict(a,locked_at=a["cutoff_at"])
        wrong=dict(a,cutoff_at="2026-11-19T11:46:00+09:00")
        reverse=dict(a,predicted_at="2026-11-19T11:44:30+09:00")
        self.assertTrue(all(not valid_record(r) for r in (late,wrong,reverse)))
        self.assertEqual(backtest([a,a])["eligible"],1)
        self.assertEqual(backtest([a,dict(a,result=[2,3,1])])["eligible"],0)
    def test_date_split_and_venue_counts(self):
        a,b=record(),record("2026-11-20")
        x=backtest([a,b])
        self.assertEqual(x["earlier_dates"]["races"],1)
        self.assertEqual(x["later_dates"]["races"],1)
        self.assertEqual(x["by_venue"]["test"]["races"],2)

    def test_no_result_reconstruction(self):
        item=record()
        item["result"]=None
        self.assertFalse(valid_record(item))

if __name__=="__main__":
    unittest.main()

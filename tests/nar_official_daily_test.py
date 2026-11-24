import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_nar_official_daily import summarize

class OfficialDailyTest(unittest.TestCase):
    def test_explicit_status_and_unknown_are_distinguished(self):
        r={"id":"r","venue":"浦和","race_no":1,"date":"2026-11-24",
           "start_at":"2026-11-24T20:00:00+09:00","cutoff_at":"2026-11-24T19:45:00+09:00",
           "locked_at":"2026-11-24T19:44:00+09:00","predicted_at":"2026-11-24T19:43:00+09:00",
           "ranking":[{"no":i} for i in range(1,7)],"result":[1,2,3],
           "payouts":{"win":200,"trio":1000,"trifecta":5000}}
        raw=["浦和","20261124","1"]+[""]*23
        raw[25]="重"
        horses=[]
        for n,rank in enumerate(["1","2","3","取消","中止","0"],1):
            row=["浦和","20261124","1","","",str(n)]+[""]*26
            row[31]=rank
            horses.append((row,{}))
        tables={"racelist":[(raw,{})],"horselist":horses,"payback":[]}
        with patch("audit_nar_official_daily.official_settlement",return_value=({"payouts":{"win":200,"trio":1100,"trifecta":5000}},None)):
            x=summarize([r],tables,"2026-11-24")
        self.assertEqual(x["coverage"]["known_ground"],1)
        self.assertEqual(x["coverage"]["stored_trio_mismatch"],1)
        self.assertEqual(x["runner_status_counts"],{"finished":3,"withdrawn":1,"did_not_finish":1,"unknown":1})
        self.assertTrue(x["race_details"][0]["refund_review_required"])
        self.assertEqual(x["venue_ground"][0]["top1_win"],1)
        y=summarize([r],tables,"2026-11-24")
        self.assertEqual(y["venue_ground"],[])
        self.assertEqual(y["coverage"]["payout_official_row_missing_or_dead_heat"],1)

if __name__=="__main__":
    unittest.main()

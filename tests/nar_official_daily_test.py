import sys
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from audit_nar_official_daily import summarize
from nar_official_status import parse_statuses

class OfficialDailyTest(unittest.TestCase):
    def test_official_result_rows_only(self):
        html = """<table><tr><td>取消</td><td>1</td><td>8</td><td>無関係</td></tr></table>
        <table><tr><th>着順</th><th>枠番</th><th>馬番</th><th>馬名</th></tr>
        <tr><td>取消</td><td>1</td><td>８</td><td>馬A</td></tr>
        <tr><td>除外</td><td>1</td><td>9</td><td>馬B</td></tr>
        <tr><td></td><td>1</td><td>10</td><td>馬C</td><td>中止</td></tr>
        <tr><td>1</td><td>2</td><td>11</td><td>馬D</td><td>中止</td></tr>
        <tr><td>取消</td><td>2</td><td>12</td><td>馬E</td></tr></table>"""
        self.assertEqual(parse_statuses(html,{8,9,10,11}),
                         {8:"withdrawn",9:"excluded",10:"did_not_finish"})
        self.assertEqual(parse_statuses("<p>取消 8</p>",{8}),{})

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
        z=summarize([r],tables,"2026-11-24",
                    lookup=lambda *args: ({6:{"status":"excluded","source":"https://www.keiba.go.jp/test"}}, "matched"))
        self.assertEqual(z["race_details"][0]["official_runner_status"]["6"],"excluded")
        self.assertEqual(z["race_details"][0]["unresolved_runner_numbers"],[])
        documented = [{"date":"2026-11-24","id":"r","no":6,
                       "status":"withdrawn","source":"https://www.keiba.go.jp/example"}]
        m=summarize([r],tables,"2026-11-24",documented_status=documented)
        d=m["race_details"][0]
        self.assertEqual(d["status_evidence"]["6"]["origin"],"documented_manual")
        self.assertEqual(d["refund_review"]["withdrawn_runner_numbers"],[4,6])
        self.assertIsNone(d["refund_review"]["actual_refund_yen"])
        c=summarize([r],tables,"2026-11-24",
                    lookup=lambda *args: ({6:{"status":"excluded","source":"https://www.keiba.go.jp/test"}}, "matched"),
                    documented_status=documented)
        self.assertEqual(c["race_details"][0]["official_runner_status"]["6"],"source_conflict")
        self.assertEqual(c["race_details"][0]["unresolved_runner_numbers"],[6])
        self.assertEqual(c["coverage"]["runner_status_conflict"],1)
        y=summarize([r],tables,"2026-11-24")
        self.assertEqual(y["venue_ground"],[])
        self.assertEqual(y["coverage"]["payout_official_row_missing_or_dead_heat"],1)

if __name__=="__main__":
    unittest.main()

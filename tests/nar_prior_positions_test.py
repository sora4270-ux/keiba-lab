import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_nar_prior_positions import early_corner, prior_summary, audit

class PriorPositionTests(unittest.TestCase):
    def test_early_not_fourth(self):
        self.assertEqual(early_corner({"コーナー名称1":"4角","コーナー通過順1":"1,2,3"}),{})
        self.assertEqual(early_corner({"コーナー名称1":"1角","コーナー通過順1":"1,2,3"})[1],1)
    def test_future_same_day_and_missing_are_excluded(self):
        runs=[(("浦和",d,1),v) for d,v in [("20261125",0),("20261124",0),("20261123",1),("20261122",.9),("20261121",.8)]]
        x=prior_summary(runs,"2026-11-24",3)
        self.assertEqual(x["position_band"],"front")
        self.assertEqual(x["mean_early_position"],.9)
        self.assertEqual(prior_summary(runs,"2026-11-24",5)["position_band"],"insufficient_history")
        runs[2]=(runs[2][0],None)
        self.assertEqual(prior_summary(runs,"2026-11-24",3)["position_band"],"insufficient_history")
    def test_ambiguous_date_not_classified(self):
        runs=[(("浦和","20261123",1),1),(("大井","20261123",2),1),(("浦和","20261122",1),1)]
        self.assertEqual(prior_summary(runs,"2026-11-24",3)["position_band"],"insufficient_history")
    def test_archive_join_and_prior_window(self):
        races=[]; horses=[]
        for d in ("20261121","20261122","20261123","20261124"):
            base={"競馬場":"浦和","競走年月日":d,"レース番号":"1"}
            raw=["浦和",d,"1","","","1"]
            races.append((raw,{**base,"コーナー名称1":"1角","コーナー通過順1":"1,2,3"}))
            horses.append((raw,{**base,"馬名":"テスト","生年月日":"20210101","馬番":"1","着順":"1"}))
        x=audit({"racelist":races,"horselist":horses})
        self.assertEqual(x["windows"]["3"]["runner_entries"],4)
        self.assertEqual(x["windows"]["3"]["front"],1)
        self.assertEqual(x["windows"]["5"]["insufficient_history"],4)

if __name__=="__main__":
    unittest.main()

import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_nar_prior_positions import early_corner, prior_summary, audit, required_months, merge_months

from audit_nar_context_history import context_audit, provisional_jockey_key, outcome_summary

class PriorPositionTests(unittest.TestCase):
    def test_provisional_jockey_is_not_stable_id(self):
        self.assertEqual(provisional_jockey_key([],{"騎手名":"矢野貴","騎手所属":"大井"}),("矢野貴","大井"))
        self.assertIsNone(provisional_jockey_key([],{"騎手名":"矢野貴"}))
        self.assertIsNone(provisional_jockey_key([],{"騎手名":"未定","騎手所属":"大井"}))
        self.assertIsNone(outcome_summary([])["top3_rate"])

    def test_context_history_prior_only_and_stable_jockey(self):
        races=[]; horses=[]
        for d in ("20261001","20261101","20261102","20261103"):
            b={"競馬場":"浦和","競走年月日":d,"レース番号":"1"}
            raw=["浦和",d,"1","","","1"]
            races.append((raw,{**b,"距離":"1400","馬場":"良"}))
            horses.append((raw,{**b,"馬名":"テスト","生年月日":"20210101","馬番":"1",
                                "着順":"1","騎手コード":"123"}))
        x=context_audit({"racelist":races,"horselist":horses},"2026-11")["coverage"]
        self.assertEqual(x["target_entries"],3)
        self.assertEqual(x["exact_distance_with_history"],3)
        self.assertEqual(x["same_ground_with_3plus"],1)
        self.assertEqual(x["jockey_venue_with_3plus"],1)
        for _,f in horses:
            f.pop("騎手コード")
        for _,f in horses:
            f["騎手名"]="テスト騎手"
            f["騎手所属"]="浦和"
        report=context_audit({"racelist":races,"horselist":horses},"2026-11")
        x=report["coverage"]
        self.assertEqual(x["target_jockey_id_known"],0)
        self.assertEqual(x["same_jockey_with_history"],0)
        self.assertEqual(report["jockey_provisional_coverage"]["name_affiliation_present"],3)
        self.assertEqual(report["prior_context_outcomes"]["exact_distance"]["prior_completed_runs_sum"],3)
        self.assertEqual(report["jockey_identity_status"],"no_stable_id")

    def test_required_months_and_no_overlapping_rows(self):
        self.assertEqual(required_months("2026-11"),["2026-11","2026-10","2026-09","2026-08"])
        raw=["浦和","20261101","1","","","1"]
        item=(raw,{"競馬場":"浦和","競走年月日":"20261101","レース番号":"1"})
        merged, counts=merge_months({"2026-11":{"racelist":[item],"horselist":[item]},
                                     "2026-10":{"racelist":[item],"horselist":[item]}})
        self.assertEqual(len(merged["racelist"]),1)
        self.assertEqual(counts["2026-10"]["horselist"],0)
        self.assertEqual(audit(merged,"2026-10")["windows"]["3"],{})
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

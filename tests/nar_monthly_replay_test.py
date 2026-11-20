import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from replay_nar_monthly import replay

def sample(day, venue="園田"):
    race={"競馬場":venue,"競走年月日":day,"レース番号":"1","距離":"1400",
          "コーナー名称1":"4角","コーナー通過順1":"1,2,3"}
    horses=[]
    for n in range(1,4):
        h={"競馬場":venue,"競走年月日":day,"レース番号":"1","馬番":str(n),
           "馬名":f"TEST{n}","生年月日":"20200101","着順":str(n),
           "タイム":str(1300+n*10)}
        horses.append(([],h))
    return {"racelist":[([],race)],"horselist":horses}

class ReplayTests(unittest.TestCase):
    def test_prior_day_only_and_ordered_across_venues(self):
        tables=[sample("20261101","高知"),sample("20261102","園田"),
                sample("20261103","高知")]
        result=replay(tables,"20261101","20261103")
        self.assertEqual(result["eligible"],2)
        self.assertEqual(result["skipped"],1)
        self.assertEqual(result["recent_form_win"],2)
        self.assertTrue(result["baseline_unavailable"])
        self.assertEqual(result["holdout"]["training"]["base"]["races"] + result["holdout"]["test"]["base"]["races"], 2)
        self.assertEqual(result["holdout"]["training"]["distance_adjusted"]["races"] + result["holdout"]["test"]["distance_adjusted"]["races"], 2)
        comparison = result["confidence_validation"]["s_vs_other"]
        self.assertEqual(comparison["S"]["races"] + comparison["non_S"]["races"],
                         result["holdout"]["test"]["base"]["races"])
        self.assertEqual(comparison["S"]["wins"] + comparison["non_S"]["wins"],
                         result["holdout"]["test"]["base"]["wins"])
        confidence = result["confidence_diagnostics"]
        self.assertEqual(sum(v["races"] for v in confidence["holdout_by_grade"].values()),
                         result["holdout"]["test"]["base"]["races"])
        self.assertEqual(len(confidence["training_margin_cutoffs"]), 3)
        diagnostics = result["error_diagnostics"]
        self.assertEqual(sum(diagnostics["finish_distribution"].values()),
                         result["holdout"]["test"]["base"]["races"])
        self.assertEqual(sum(x["races"] for x in diagnostics["by_venue"].values()),
                         result["holdout"]["test"]["base"]["races"])
        self.assertEqual(sum(x["races"] for x in diagnostics["by_distance"].values()),
                         result["holdout"]["test"]["base"]["races"])
        self.assertEqual(sum(x["races"] for x in diagnostics["by_prior_runs"].values()),
                         result["holdout"]["test"]["base"]["races"])
        self.assertIn(result["holdout"]["selected_on_training_only"], ("base", "coverage_adjusted", "distance_adjusted"))

    def test_frozen_cutoffs_cover_all_eligible_races(self):
        tables=[sample("20261101"),sample("20261102"),sample("20261103")]
        result=replay(tables,"20261101","20261103",
                      frozen_cutoffs=[0.02511,0.05710,0.11511])
        frozen=result["frozen_confidence_validation"]
        self.assertEqual(sum(v["races"] for v in frozen["by_grade"].values()),
                         result["eligible"])
        self.assertEqual(frozen["S_vs_non_S"]["S"]["wins"] +
                         frozen["S_vs_non_S"]["non_S"]["wins"], result["recent_form_win"])
        with self.assertRaises(ValueError):
            replay(tables,"20261101","20261103",frozen_cutoffs=[0.1,0.05,0.2])

    def test_no_prior_history(self):
        result=replay([sample("20261101")],"20261101","20261101")
        self.assertEqual(result["eligible"],0)
        self.assertIsNone(result["recent_form_win_rate"])
        self.assertEqual(result["holdout"]["test"]["base"]["races"], 0)
        self.assertEqual(result["confidence_diagnostics"]["holdout_by_grade"], {})
        self.assertIsNone(result["confidence_validation"]["s_vs_other"]["S"]["win_rate_wilson95"])

if __name__=="__main__":
    unittest.main()

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

    def test_no_prior_history(self):
        result=replay([sample("20261101")],"20261101","20261101")
        self.assertEqual(result["eligible"],0)
        self.assertIsNone(result["recent_form_win_rate"])

if __name__=="__main__":
    unittest.main()

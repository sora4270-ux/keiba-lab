import sys
import datetime as dt
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_nar_confidence_multimonth import audit_months, reliability, rolling_months
from nar_feature_stake_audit_test import fake


def official_table():
    raw=[""]*54
    raw[0:3]=["大井","20261119","1"]
    for i,v in {4:1,5:500,32:1,33:2,34:220,36:1,37:3,38:330,
                40:2,41:3,42:450,44:1,45:2,46:3,47:1400,
                49:1,50:2,51:3,52:8500}.items():
        raw[i]=str(v)
    return {"payback":[(raw,{})]}


def frozen():
    r=fake()
    for row,p in zip(r["ranking"],[.6,.2,.1,.05,.03,.02]):
        row["win_probability"]=p
    r["market_at_lock"]={"updated_at":"2026-11-19T11:42+09:00",
                         "horses":[{"no":i,"odds":2.0} for i in range(1,7)]}
    return r


class MultiMonthTests(unittest.TestCase):
    def test_reliability_measures_probability_not_roi(self):
        report=reliability([frozen()],official_table())
        self.assertEqual(report["by_grade"]["S"]["races"],1)
        self.assertEqual(report["by_grade"]["S"]["actual_win_percent"],100)
        self.assertEqual(report["by_grade"]["S"]["mean_predicted_win_percent"],60)
        self.assertEqual(report["by_grade"]["S"]["brier_score"],.16)
    def test_missing_month_is_not_presented_as_verified(self):
        r=audit_months([frozen()],{"2026-11":official_table()},["2026-10","2026-11"])
        self.assertFalse(r["multi_month_validated"])
        self.assertEqual(r["verified_month_count"],1)
        self.assertEqual(r["months"]["2026-10"]["status"],"official_archive_unavailable")
    def test_official_archive_without_forecast_is_not_validation(self):
        r=audit_months([frozen()],{"2026-10":official_table(),"2026-11":official_table()},["2026-10","2026-11"])
        self.assertEqual(r["months"]["2026-10"]["status"],"no_frozen_predictions")
        self.assertFalse(r["multi_month_validated"])
    def test_rolling_months_cross_year(self):
        self.assertEqual(rolling_months(dt.date(2027,1,2),3),['2026-11','2026-12','2027-01'])
    def test_zero_officially_eligible_is_not_audited(self):
        t=official_table()
        t['payback'][0][0][4]='2'
        r=audit_months([frozen()],{'2026-11':t},['2026-11'])
        self.assertEqual(r['verified_month_count'],0)
        self.assertEqual(r['months']['2026-11']['status'],'no_officially_eligible_races')
    def test_wrong_official_winner_excluded(self):
        t=official_table()
        row=t["payback"][0][0]
        row[4]="2"
        self.assertEqual(reliability([frozen()],t)["all"]["races"],0)


if __name__=="__main__":
    unittest.main()

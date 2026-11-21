import itertools
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from audit_nar_confidence_wide import grade_from_frozen, paired
from nar_feature_stake_audit_test import fake


class ConfidenceWideTests(unittest.TestCase):
    def test_grade_and_market_cap(self):
        r=fake()
        for row,p in zip(r["ranking"],[.60,.20,.10,.05,.03,.02]):
            row["win_probability"]=p
        self.assertEqual(grade_from_frozen(r)[0],"B") # no authenticated prelock market
        r["market_at_lock"]={"updated_at":"2026-11-19T11:42+09:00",
                             "horses":[{"no":i,"odds":2.0} for i in range(1,7)]}
        self.assertEqual(grade_from_frozen(r)[0],"S")
        r["market_at_lock"]["updated_at"]="2026-11-19T11:00+09:00"
        self.assertEqual(grade_from_frozen(r)[0],"B")
    def test_incomplete_ranking_skips(self):
        r=fake()
        r["ranking"]=r["ranking"][:5]
        self.assertEqual(grade_from_frozen(r)[1],"fewer_than_six_ranked")
    def test_no_future_result_changes_grade(self):
        a=fake(result=[1,2,3])
        b=fake(result=[3,2,1])
        for r in (a,b):
            for row,p in zip(r["ranking"],[.4,.25,.15,.1,.06,.04]):
                row["win_probability"]=p
        self.assertEqual(grade_from_frozen(a),grade_from_frozen(b))


if __name__=="__main__":
    unittest.main()

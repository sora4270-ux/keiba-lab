import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from update_nar import observed_feature_shadow

class ObservedFeatureValidationTests(unittest.TestCase):
    def test_available_pre_race_fields_only(self):
        race={"horses":[
            {"no":1,"distance":(2,10),"venue":(1,10),"jockey":(3,20),"overall":(4,30)},
            {"no":2,"distance":(5,10),"venue":(4,10),"jockey":(4,20),"overall":(6,30)},
            {"no":3,"distance":None,"venue":None,"jockey":None,"overall":None},
        ],"recent_features":[(.8,3),(.4,2),None]}
        result=observed_feature_shadow(race)
        # Only two runners have valid scores: abstention is intentional.
        self.assertIsNone(result["top_no"])
        self.assertEqual(result["ranking"][0]["no"], 1)
        self.assertEqual(result["ranking"][0]["coverage"],5)
        self.assertIsNone(result["ranking"][2]["score"])
        self.assertIn("carried_weight",result["missing"])

    def test_does_not_consume_result_or_future_data(self):
        race={"horses":[{"no":1,"distance":(2,5)},{"no":2,"distance":(1,5)},{"no":3,"distance":(0,5)}]}
        first=observed_feature_shadow(race)
        race["result"]=[3,2,1]
        race["horses"][0]["rank"]=3
        race["horses"][2]["rank"]=1
        self.assertEqual(first,observed_feature_shadow(race))

    def test_insufficient_coverage(self):
        race={"horses":[{"no":1},{"no":2}]}
        self.assertIsNone(observed_feature_shadow(race)["top_no"])

if __name__=="__main__":
    unittest.main()

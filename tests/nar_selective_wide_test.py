import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from backtest_nar_selective_wide import wager

class SelectiveWideTests(unittest.TestCase):
    def setUp(self):
        self.info={"wide":{(1,2):500,(1,3):700,(2,3):800,(2,4):900}}
        self.rank=[1,2,3,4,5,6]
    def test_top3_900_stake_and_payout(self):
        spent,paid,_=wager(self.info,self.rank,"S","top3_all","大井")
        self.assertEqual((spent,paid),(900,6000))
    def test_c_skips(self):
        self.assertEqual(wager(self.info,self.rank,"C","grade_budget","大井")[:2],(0,0))
    def test_grade_budget_s_600(self):
        self.assertEqual(wager(self.info,self.rank,"S","grade_budget","大井")[:2],(600,4000))
    def test_flat_only_excludes_banei(self):
        self.assertEqual(wager(self.info,self.rank,"S","selective_s_a_flat","帯広")[:2],(0,0))
    def test_a_three_point_600(self):
        self.assertEqual(wager(self.info,self.rank,"A","selective_s_a","大井")[0],600)
    def test_box_requires_100_yen_per_pair(self):
        self.assertEqual(wager(self.info,self.rank,"B","confidence_box","大井")[0],1000)

if __name__=="__main__":
    unittest.main()

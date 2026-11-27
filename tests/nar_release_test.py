import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from audit_nar_release import metrics,calibration,analyze
from audit_nar_ev_staking_shadow import valid_quote
class ReleaseTest(unittest.TestCase):
 def test_partial_hits_are_net_losses(self):
  rows=[{'date':'2026-11-01','stake_yen':100,'return_yen':50},{'date':'2026-11-02','stake_yen':100,'return_yen':0},{'date':'2026-11-03','stake_yen':100,'return_yen':400}]
  x=metrics(rows);self.assertEqual(x['net_yen'],150);self.assertEqual(x['max_consecutive_net_losses'],2);self.assertEqual(x['max_drawdown_yen'],150)
 def test_missing_never_approved(self):
  x=analyze([],{}, {'entries':[]});self.assertFalse(x['real_money_allowed']);self.assertEqual(x['verified_diagnostic_races'],0);self.assertIsNone(x['methods']['win_top1']['all']['roi_percent'])
 def test_calibration_does_not_mutate(self):
  rows=[{'probability':.9,'won':0}];x=calibration(rows,.2);self.assertLess(x['mean_probability'],1);self.assertEqual(rows[0]['probability'],.9)
 def test_duplicate_and_nonfinite_odds_rejected(self):
  r={'market_at_lock':{'updated_at':'2026-11-01T11:00:00+09:00','horses':[{'no':1,'odds':2},{'no':1,'odds':3}]},'locked_at':'2026-11-01T11:01:00+09:00','cutoff_at':'2026-11-01T11:15:00+09:00','start_at':'2026-11-01T11:30:00+09:00','ranking':[{'no':1}]}
  self.assertEqual(valid_quote(r)[1],'duplicate_market_horse');r['market_at_lock']['horses']=[{'no':1,'odds':float('nan')}];self.assertEqual(valid_quote(r)[1],'invalid_market')
if __name__=='__main__':unittest.main()

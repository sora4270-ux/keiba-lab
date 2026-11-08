import sys, unittest, datetime as dt
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from update_nar import learn_parameters
from trio_strategy import calibration_for_podium
class QualityTest(unittest.TestCase):
    def record(self, observed):
        return {'ranking':[{'no':i,'form_probability':1/3,'win_probability':1/3} for i in (1,2,3)],'result':[1,2,3], 'settled_at':'2026-11-08T13:00:00+09:00','locked_at':'2026-11-08T12:00:00+09:00','cutoff_at':'2026-11-08T12:05:00+09:00','market_at_lock':{'updated_at':observed,'horses':[{'no':i,'odds':3} for i in (1,2,3)]}}
    def test_only_recent_prelock_quotes_train_market_weights(self):
        now=dt.datetime.fromisoformat('2026-11-08T14:00:00+09:00')
        rows=[self.record(t) for t in ['2026-11-08T11:45:00+09:00','2026-11-08T11:44:59+09:00','2026-11-08T12:01:00+09:00']]
        self.assertEqual(learn_parameters(rows,now)['market_training_races'],1)
        self.assertEqual(calibration_for_podium(rows,now)['podium_training_races'],1)
if __name__=='__main__': unittest.main()

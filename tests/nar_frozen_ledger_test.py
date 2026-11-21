import datetime as dt
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from record_nar_frozen_ledger import update_ledger


class FrozenLedgerTests(unittest.TestCase):
    def setUp(self):
        self.r={"id":"nar-test","cutoff_at":"2026-11-22T12:45:00+09:00",
                "locked_at":"2026-11-22T12:40:00+09:00","ranking":[{"no":1,"win_probability":.7}]}
        self.base={"schema_version":1,"entries":[]}
        self.seen="2026-11-22T03:42:00+00:00"
    def test_first_seen_before_cutoff(self):
        out,n=update_ledger({"races":[self.r]},self.base,self.seen)
        self.assertEqual(n,1)
        self.assertEqual(out["entries"][0]["observation_status"],"observed_before_cutoff")
    def test_same_record_is_idempotent(self):
        out,_=update_ledger({"races":[self.r]},self.base,self.seen)
        again,n=update_ledger({"races":[self.r]},out,"2026-11-23T00:00:00+00:00")
        self.assertEqual(n,0)
        self.assertEqual(again,out)
    def test_immutable_change_rejected(self):
        out,_=update_ledger({"races":[self.r]},self.base,self.seen)
        modified={**self.r,"ranking":[{"no":2,"win_probability":.7}]}
        with self.assertRaisesRegex(RuntimeError,"snapshot changed"):
            update_ledger({"races":[modified]},out,self.seen)
    def test_result_update_is_allowed(self):
        out,_=update_ledger({"races":[self.r]},self.base,self.seen)
        _,n=update_ledger({"races":[{**self.r,"result":[1,2,3]}]},out,self.seen)
        self.assertEqual(n,0)
    def test_missing_history_rejected(self):
        out,_=update_ledger({"races":[self.r]},self.base,self.seen)
        with self.assertRaisesRegex(RuntimeError,"history missing"):
            update_ledger({"races":[]},out,self.seen)
    def test_historical_import_not_authentic(self):
        out,_=update_ledger({"races":[self.r]},self.base,"2026-11-23T00:00:00+00:00")
        self.assertEqual(out["entries"][0]["observation_status"],"historical_import_not_authenticated")
    def test_duplicate_ids_rejected(self):
        with self.assertRaisesRegex(ValueError,"duplicate"):
            update_ledger({"races":[self.r,self.r]},self.base,self.seen)


if __name__=="__main__":
    unittest.main()

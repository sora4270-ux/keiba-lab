import datetime as dt
import unittest
from scripts.audit_trifecta_banei import audit


class TrifectaAuditTest(unittest.TestCase):
    def race(self, shadow=None):
        at = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.timezone(dt.timedelta(hours=9)))
        r = {
            "id": "test", "venue": "高知", "result": [1, 2, 3],
            "ranking": [{"no": 1}], "tickets": [[1, 2, 3], [2, 1, 3]],
            "payouts": {"trifecta": 1500},
            "predicted_at": at.isoformat(),
            "locked_at": at.isoformat(),
            "cutoff_at": (at + dt.timedelta(minutes=1)).isoformat(),
            "trifecta_market_at_lock": {"updated_at": at.isoformat(), "odds": {"1-2-3": 15}},
        }
        if shadow is not None:
            r["trifecta_value_shadow"] = shadow
        return r

    def test_old_and_new_same_race(self):
        r = self.race({"status": "candidate", "tickets": [[1, 2, 3]], "stake_yen": 100})
        a = audit([r])
        self.assertEqual(a["old_comparable"]["stake_yen"], 200)
        self.assertEqual(a["old_comparable"]["return_yen"], 1500)
        self.assertEqual(a["new_shadow"]["return_yen"], 1500)
        self.assertEqual(a["new_shadow"]["roi_percent"], 1500)
        self.assertEqual(a["new_shadow"]["evaluated_candidates"], 1)

    def test_skip_is_not_a_purchase(self):
        a = audit([self.race({"status": "skip", "tickets": [], "stake_yen": 0})])
        self.assertEqual(a["new_shadow"]["settled_comparable"], 1)
        self.assertIsNone(a["new_shadow"]["roi_percent"])
        self.assertEqual(a["decision"], "insufficient_new_shadow_data")

    def test_future_quote_is_rejected(self):
        r = self.race()
        r["trifecta_market_at_lock"]["updated_at"] = "2026-11-22T12:01:00+09:00"
        a = audit([r])
        self.assertEqual(a["prelock_trifecta_quotes"], 0)
        self.assertEqual(a["old_comparable"]["races"], 0)


if __name__ == "__main__":
    unittest.main()

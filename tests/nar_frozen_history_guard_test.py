import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from update_nar import verify_history_preserved, update_data
import datetime as dt


class FrozenHistoryGuardTests(unittest.TestCase):
    def test_new_records_allowed(self):
        verify_history_preserved({"races": [{"id": "old"}]},
                                 {"races": [{"id": "old"}, {"id": "new"}]})

    def test_deleted_record_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "drop 1"):
            verify_history_preserved({"races": [{"id": "old"}]}, {"races": []})

    def test_duplicate_new_records_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            verify_history_preserved({"races": []},
                                     {"races": [{"id": "same"}, {"id": "same"}]})

    def test_invalid_existing_record_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "invalid race IDs"):
            verify_history_preserved({"races": [{"foo": 1}]}, {"races": []})

    def test_history_over_5000_records_must_not_be_truncated(self):
        previous = {"races": [{"id": str(i)} for i in range(5001)]}
        with self.assertRaisesRegex(RuntimeError, "drop 1"):
            verify_history_preserved(previous, {"races": previous["races"][:5000]})
        verify_history_preserved(previous, {"races": previous["races"]})

    def test_frozen_ranking_change_rejected(self):
        old = {"races": [{"id": "race", "ranking": [{"no": 1}]}]}
        new = {"races": [{"id": "race", "ranking": [{"no": 2}]}]}
        with self.assertRaisesRegex(RuntimeError, "frozen ranking"):
            verify_history_preserved(old, new)

    def test_frozen_tickets_change_rejected(self):
        old = {"races": [{"id": "race", "tickets": [[1, 2, 3]]}]}
        new = {"races": [{"id": "race", "tickets": [[1, 2, 4]]}]}
        with self.assertRaisesRegex(RuntimeError, "frozen tickets"):
            verify_history_preserved(old, new)

    def test_frozen_strategy_v5_change_rejected(self):
        old = {"races": [{"id": "race", "strategy_v5": {"tickets": [[1, 2, 3]]}}]}
        new = {"races": [{"id": "race", "strategy_v5": {"tickets": [[1, 2, 4]]}}]}
        with self.assertRaisesRegex(RuntimeError, "frozen strategy_v5"):
            verify_history_preserved(old, new)

    def test_frozen_market_snapshot_change_rejected(self):
        old = {"races": [{"id": "race", "market_at_lock": {"updated_at": "before"}}]}
        new = {"races": [{"id": "race", "market_at_lock": {"updated_at": "after"}}]}
        with self.assertRaisesRegex(RuntimeError, "frozen market_at_lock"):
            verify_history_preserved(old, new)

    def test_mutable_display_market_allowed(self):
        old = {"races": [{"id": "race", "market": {"horses": []}}]}
        new = {"races": [{"id": "race", "market": {"horses": [{"no": 1}]}}]}
        verify_history_preserved(old, new)

    def test_result_settlement_allowed(self):
        old = {"races": [{"id": "race", "ranking": [{"no": 1}], "result": None}]}
        new = {"races": [{"id": "race", "ranking": [{"no": 1}], "result": [1, 2, 3]}]}
        verify_history_preserved(old, new)

    def test_update_does_not_mutate_persisted_record(self):
        now = dt.datetime(2026, 11, 21, 12, tzinfo=dt.timezone(dt.timedelta(hours=9)))
        previous = {"races": [{"id": "old", "date": "2026-11-20",
                               "start_at": "2026-11-20T12:00:00+09:00",
                               "ranking": [{"no": 1}], "tickets": [[1, 2, 3]]}],
                    "drafts": []}
        original = previous["races"][0]
        try:
            result = update_data([], now, previous)[0]
        except (KeyError, ValueError, TypeError) as exc:
            self.fail(f"Existing valid history should survive a no-races update: {exc}")
        self.assertIsNot(result["races"][0], original)
        self.assertEqual(previous["races"][0]["ranking"], [{"no": 1}])
        result["races"][0]["ranking"][0]["no"] = 9
        self.assertEqual(previous["races"][0]["ranking"], [{"no": 1}])
        with self.assertRaisesRegex(RuntimeError, "frozen ranking"):
            verify_history_preserved(previous, result)

    def test_first_run_allowed(self):
        verify_history_preserved({}, {"races": []})


if __name__ == "__main__":
    unittest.main()

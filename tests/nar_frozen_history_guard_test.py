import sys
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from update_nar import verify_history_preserved


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

    def test_first_run_allowed(self):
        verify_history_preserved({}, {"races": []})


if __name__ == "__main__":
    unittest.main()

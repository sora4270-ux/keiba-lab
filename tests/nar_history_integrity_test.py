import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from update_nar import load_persisted_history


class PersistedHistoryTests(unittest.TestCase):
    def test_missing_file_allows_first_run(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(load_persisted_history(Path(d) / "missing.json"), {})

    def test_valid_history_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "history.json"
            value = {"races": [{"id": "nar-20261101-大井-01"}], "drafts": []}
            path.write_text(json.dumps(value), encoding="utf-8")
            self.assertEqual(load_persisted_history(path), value)

    def test_empty_file_rejected_without_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "history.json"
            path.write_text("", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "empty"):
                load_persisted_history(path)
            self.assertEqual(path.read_text(encoding="utf-8"), "")

    def test_corrupt_json_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "history.json"
            path.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "invalid JSON"):
                load_persisted_history(path)

    def test_missing_races_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "history.json"
            path.write_text('{"drafts":[]}', encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "invalid schema"):
                load_persisted_history(path)


if __name__ == "__main__":
    unittest.main()

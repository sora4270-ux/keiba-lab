import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from inspect_nar_history import inspect


class HistoryInspectionTests(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(inspect(Path(d) / "none.json")["status"], "missing")

    def test_empty(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "history.json"
            path.write_text("")
            self.assertEqual(inspect(path)["status"], "empty")

    def test_valid_counts_without_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "history.json"
            value = {"races": [{"id": "one"}], "drafts": [{}, {}]}
            path.write_text(json.dumps(value))
            before = path.read_bytes()
            self.assertEqual(inspect(path)["frozen_count"], 1)
            self.assertEqual(inspect(path)["draft_count"], 2)
            self.assertEqual(path.read_bytes(), before)

    def test_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "history.json"
            path.write_text("{")
            self.assertEqual(inspect(path)["status"], "invalid_json")

    def test_invalid_schema(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "history.json"
            path.write_text('{"races":{}}')
            self.assertEqual(inspect(path)["status"], "invalid_schema")


if __name__ == "__main__":
    unittest.main()

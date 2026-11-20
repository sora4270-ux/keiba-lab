import datetime as dt
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_nar_freshness import assess

NOW = dt.datetime(2026, 11, 21, 9, tzinfo=dt.timezone.utc)


class FreshnessTest(unittest.TestCase):
    def test_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(assess(Path(directory) / "missing", NOW)["status"], "missing")

    def check(self, payload, expected):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "health.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            self.assertEqual(assess(path, NOW)["status"], expected)

    def test_recent_success(self):
        self.check({"completed_at": "2026-11-21T08:00:00+00:00", "status": "success"}, "healthy")

    def test_stale_success(self):
        self.check({"completed_at": "2026-11-20T15:04:46+00:00", "status": "success"}, "stale")

    def test_recent_failure(self):
        self.check({"completed_at": "2026-11-21T08:00:00+00:00", "status": "failed"}, "last_refresh_failed")

    def test_future_timestamp(self):
        self.check({"completed_at": "2026-11-21T09:30:00+00:00", "status": "success"}, "future_timestamp")

    def test_invalid_timestamp(self):
        self.check({"completed_at": "not-a-date", "status": "success"}, "invalid")


if __name__ == "__main__":
    unittest.main()

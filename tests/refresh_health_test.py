import datetime as dt
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from refresh_nar import run_refresh


class RefreshHealthTest(unittest.TestCase):
    def test_failure_recovery_unchanged_and_odds_partial(self):
        with tempfile.TemporaryDirectory() as folder:
            data, health = Path(folder) / 'predictions.json', Path(folder) / 'health.json'
            payload = {'schema_version': 1, 'races': [{'tickets': [[1, 2, 3]]}],
                       'odds_feed': {'status': 'unavailable'}}
            data.write_text(json.dumps(payload))
            frozen = data.read_bytes()
            moment = dt.datetime(2026, 11, 18, tzinfo=dt.timezone.utc)
            def clock():
                nonlocal moment
                moment += dt.timedelta(minutes=1)
                return moment.isoformat()
            def refresh(runner):
                code = run_refresh(data, health, runner, clock)
                return code, json.loads(health.read_text())
            code, first = refresh(Mock(return_value=subprocess.CompletedProcess([], 0)))
            self.assertEqual(code, 0)
            self.assertFalse(first['content_changed'])
            self.assertEqual(first['frozen_forecast_count'], 1)
            self.assertEqual(first['history_status'], 'valid')
            self.assertEqual(first['odds_status'], 'unavailable')
            for count in (1, 2):
                code, failed = refresh(Mock(return_value=subprocess.CompletedProcess([], 1)))
                self.assertEqual(code, 1)
                self.assertEqual(failed['consecutive_failures'], count)
                self.assertEqual(failed['last_success_at'], first['last_success_at'])
                self.assertIsNone(failed['content_changed'])
            code, recovered = refresh(Mock(return_value=subprocess.CompletedProcess([], 0)))
            self.assertEqual(code, 0)
            self.assertEqual(recovered['consecutive_failures'], 0)
            self.assertGreater(recovered['last_success_at'], first['last_success_at'])
            self.assertEqual(recovered['last_failure_at'], failed['last_failure_at'])
            self.assertEqual(data.read_bytes(), frozen)
            def changed(*args, **kwargs):
                data.write_text(json.dumps({**payload, 'odds_feed': {'status': 'available'}}))
                return subprocess.CompletedProcess([], 0)
            _, updated = refresh(changed)
            self.assertTrue(updated['content_changed'])
            self.assertEqual(updated['odds_status'], 'available')

    def test_empty_history_is_reported_without_running_update(self):
        with tempfile.TemporaryDirectory() as folder:
            data, health = Path(folder) / 'predictions.json', Path(folder) / 'health.json'
            data.write_text('', encoding='utf-8')
            runner = Mock()
            self.assertEqual(run_refresh(data, health, runner), 1)
            runner.assert_not_called()
            self.assertEqual(json.loads(health.read_text())['error_code'],
                             'empty_forecast_history')
            self.assertEqual(json.loads(health.read_text())['history_status'], 'empty')
            self.assertIsNone(json.loads(health.read_text())['frozen_forecast_count'])
            self.assertEqual(data.read_text(), '')

    def test_corrupt_history_is_reported_without_running_update(self):
        with tempfile.TemporaryDirectory() as folder:
            data, health = Path(folder) / 'predictions.json', Path(folder) / 'health.json'
            data.write_text('{broken', encoding='utf-8')
            runner = Mock()
            self.assertEqual(run_refresh(data, health, runner), 1)
            runner.assert_not_called()
            self.assertEqual(json.loads(health.read_text())['error_code'],
                             'invalid_forecast_history')

    def test_timeout_and_invalid_output(self):
        with tempfile.TemporaryDirectory() as folder:
            data, health = Path(folder) / 'predictions.json', Path(folder) / 'health.json'
            for runner in (Mock(side_effect=subprocess.TimeoutExpired('private-url', 900)),
                           Mock(return_value=subprocess.CompletedProcess([], 0))):
                self.assertEqual(run_refresh(data, health, runner), 1)
                record = json.loads(health.read_text())
                self.assertEqual(record['status'], 'failed')
                self.assertIsNone(record['last_success_at'])
                self.assertNotIn('private-url', health.read_text())


if __name__ == '__main__':
    unittest.main()

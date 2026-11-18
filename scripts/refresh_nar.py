"""Record every completed refresh independently of forecast content changes."""
import datetime as dt
import json
from pathlib import Path
import subprocess
import sys

DATA = Path('data/auto/nar_predictions.json')
HEALTH = Path('data/auto/nar_health.json')


def timestamp():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec='seconds')


def run_refresh(data=DATA, health=HEALTH, run=subprocess.run, clock=timestamp):
    try:
        previous = json.loads(health.read_text(encoding='utf-8'))
        if not isinstance(previous, dict):
            previous = {}
    except (OSError, ValueError):
        previous = {}
    before = data.read_bytes() if data.exists() else None
    attempt = clock()
    code, error = 1, None
    try:
        result = run([sys.executable, 'scripts/update_nar.py'], check=False, timeout=900)
        code = result.returncode
        if code:
            error = 'refresh_failed'
        else:
            payload = json.loads(data.read_text(encoding='utf-8'))
            if payload.get('schema_version') != 1 or not isinstance(payload.get('races'), list):
                raise ValueError('Invalid forecast output')
    except subprocess.TimeoutExpired:
        error = 'timeout'
    except (OSError, ValueError):
        error = 'invalid_output_or_execution'
    success = code == 0 and error is None
    completed = clock()
    record = {
        'schema_version': 1,
        'last_attempt_at': attempt,
        'completed_at': completed,
        'last_success_at': completed if success else previous.get('last_success_at'),
        'last_failure_at': previous.get('last_failure_at') if success else completed,
        'consecutive_failures': 0 if success else int(previous.get('consecutive_failures', 0)) + 1,
        'status': 'success' if success else 'failed',
        'content_changed': data.read_bytes() != before if success else None,
        'odds_status': payload.get('odds_feed', {}).get('status', 'unknown') if success else 'unknown',
        # Never publish exception strings, request URLs, or credentials.
        'error_code': error,
    }
    health.parent.mkdir(parents=True, exist_ok=True)
    temp = health.with_suffix('.tmp')
    temp.write_text(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    temp.replace(health)
    print('NAR refresh:', record['status'], 'consecutive failures:', record['consecutive_failures'])
    return 0 if success else 1


if __name__ == '__main__':
    sys.exit(run_refresh())

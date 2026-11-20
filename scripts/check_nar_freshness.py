#!/usr/bin/env python3
"""Read-only CI watchdog for NAR refresh health."""
import argparse
import datetime as dt
import json
from pathlib import Path

DEFAULT = Path("data/auto/nar_health.json")


def assess(path=DEFAULT, now=None, max_age_minutes=180):
    now = now or dt.datetime.now(dt.timezone.utc)
    if not path.exists():
        return {"status": "missing", "age_minutes": None}
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict):
            raise ValueError("not an object")
        raw = record["completed_at"]
        completed = dt.datetime.fromisoformat(raw)
        if completed.tzinfo is None:
            raise ValueError("timezone missing")
        age = (now - completed.astimezone(dt.timezone.utc)).total_seconds() / 60
    except (OSError, ValueError, TypeError, KeyError):
        return {"status": "invalid", "age_minutes": None}
    if age < -5:
        status = "future_timestamp"
    elif age > max_age_minutes:
        status = "stale"
    elif record.get("status") != "success":
        status = "last_refresh_failed"
    else:
        status = "healthy"
    return {"status": status, "age_minutes": round(age, 1)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=DEFAULT)
    parser.add_argument("--max-age-minutes", type=int, default=180)
    args = parser.parse_args()
    report = assess(args.path, max_age_minutes=args.max_age_minutes)
    print(json.dumps(report, ensure_ascii=False))
    if report["status"] != "healthy":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

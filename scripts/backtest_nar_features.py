#!/usr/bin/env python3
"""Leakage-safe NAR historical comparison of immutable pre-race predictions."""
import argparse
import datetime as dt
import json
from pathlib import Path


def valid_record(r):
    if r.get("status") == "draft" or r.get("result_alternatives"):
        return False
    result = r.get("result")
    rows = r.get("ranking")
    feature = r.get("feature_validation") or {}
    if not isinstance(result, list) or len(result) != 3 or not isinstance(rows, list) or len(rows) < 3:
        return False
    if len(set(result)) != 3 or any(type(n) is not int or n < 1 for n in result):
        return False
    try:
        locked = dt.datetime.fromisoformat(r["locked_at"])
        cutoff = dt.datetime.fromisoformat(r["cutoff_at"])
        if locked.tzinfo is None or cutoff.tzinfo is None or locked > cutoff:
            return False
        predicted = dt.datetime.fromisoformat(r["predicted_at"])
        if predicted.tzinfo is None or predicted > cutoff:
            return False
    except (KeyError, ValueError, TypeError):
        return False
    ids = [x.get("no") for x in rows if isinstance(x, dict)]
    if len(ids) != len(rows) or len(set(ids)) != len(ids) or any(type(n) is not int for n in ids):
        return False
    if any(n not in ids for n in result):
        return False
    shadow = feature.get("top_no")
    if type(shadow) is not int or shadow not in ids:
        return False
    return True


def backtest(records):
    eligible = sorted((r for r in records if valid_record(r)),
                      key=lambda r: (r["date"], r.get("start_at", ""), r.get("id", "")))
    out = {"eligible": len(eligible), "skipped": len(records)-len(eligible),
           "first_date": eligible[0]["date"] if eligible else None,
           "last_date": eligible[-1]["date"] if eligible else None,
           "model": {"win": 0, "top3": 0}, "observed_features": {"win": 0, "top3": 0}}
    for r in eligible:
        winner, podium = r["result"][0], set(r["result"])
        for label, no in (("model", r["ranking"][0]["no"]),
                          ("observed_features", r["feature_validation"]["top_no"])):
            out[label]["win"] += no == winner
            out[label]["top3"] += no in podium
    for label in ("model", "observed_features"):
        for k in ("win", "top3"):
            out[label][k+"_rate"] = round(100*out[label][k]/len(eligible), 2) if eligible else None
    out["method"] = "Same-race paired comparison, saved pre-race snapshots only; no refitting or post-race features."
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/auto/nar_predictions.json")
    parser.add_argument("--output", default="data/auto/nar_backtest.json")
    args = parser.parse_args()
    source = Path(args.input)
    if not source.exists():
        raise SystemExit("No historical prediction file; cannot claim a backtest result.")
    payload = json.loads(source.read_text(encoding="utf-8"))
    records = payload.get("races", [])
    if not isinstance(records, list):
        raise SystemExit("Invalid race list")
    report = backtest(records)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Leakage-safe NAR historical comparison of immutable pre-race predictions."""
import argparse
import datetime as dt
from collections import Counter, defaultdict
import json
from pathlib import Path


def valid_record(r):
    if not isinstance(r, dict) or r.get("status") == "draft" or r.get("result_alternatives"):
        return False
    result = r.get("result")
    rows = r.get("ranking")
    feature = r.get("feature_validation") or {}
    if not isinstance(feature, dict) or not isinstance(r.get("date"), str):
        return False
    if not isinstance(result, list) or len(result) != 3 or not isinstance(rows, list) or len(rows) < 3:
        return False
    if any(type(n) is not int or not 1 <= n <= 30 for n in result) or len(set(result)) != 3:
        return False
    try:
        locked = dt.datetime.fromisoformat(r["locked_at"])
        cutoff = dt.datetime.fromisoformat(r["cutoff_at"])
        predicted = dt.datetime.fromisoformat(r["predicted_at"])
        start = dt.datetime.fromisoformat(r["start_at"])
        if not all(x.tzinfo is not None for x in (locked, cutoff, predicted, start)):
            return False
        if not predicted <= locked < cutoff == start - dt.timedelta(minutes=15):
            return False
        if dt.date.fromisoformat(r["date"]) != start.date():
            return False
    except (KeyError, ValueError, TypeError):
        return False
    ids = [x.get("no") for x in rows if isinstance(x, dict)]
    if len(ids) != len(rows) or any(type(n) is not int or not 1 <= n <= 30 for n in ids) or len(set(ids)) != len(ids):
        return False
    # An actual finisher absent from the frozen ranking remains a miss.
    # Dropping surprises would inflate accuracy.
    shadow = feature.get("top_no")
    if type(shadow) is not int or shadow not in ids:
        return False
    return True


def _scores(records):
    n = len(records)
    out = {"races": n, "model": {"win":0,"top3":0},
           "observed_features":{"win":0,"top3":0}}
    for r in records:
        winner, podium = r["result"][0], set(r["result"])
        for label, no in (("model",r["ranking"][0]["no"]),
                          ("observed_features",r["feature_validation"]["top_no"])):
            out[label]["win"] += no == winner
            out[label]["top3"] += no in podium
    for label in ("model","observed_features"):
        for k in ("win","top3"):
            out[label][k+"_rate"] = round(100*out[label][k]/n,2) if n else None
    return out


def backtest(records):
    if not isinstance(records, list):
        raise ValueError("races must be a list")
    by_id = defaultdict(list)
    exclusions = Counter()
    for r in records:
        if not isinstance(r, dict):
            exclusions["invalid_record"] += 1
            continue
        ident = r.get("id")
        if not isinstance(ident, str) or not ident:
            exclusions["missing_id"] += 1
            continue
        by_id[ident].append(r)
    eligible = []
    for group in by_id.values():
        if any(r != group[0] for r in group[1:]):
            exclusions["conflicting_id"] += len(group)
            continue
        if len(group)>1:
            exclusions["duplicate_id"] += len(group)-1
        if valid_record(group[0]):
            eligible.append(group[0])
        else:
            exclusions["invalid_or_unverifiable_snapshot"] += 1
    eligible.sort(key=lambda r:(r["date"],r["start_at"],r["id"]))
    scores = _scores(eligible)
    days = sorted({r["date"] for r in eligible})
    split = max(1, int(len(days)*.7)) if len(days)>1 else len(days)
    early = set(days[:split])
    venues = defaultdict(list)
    for r in eligible:
        venues[str(r.get("venue") or "unknown")].append(r)
    return {"eligible":len(eligible),"skipped":len(records)-len(eligible),
            "excluded":dict(exclusions),"first_date":days[0] if days else None,
            "last_date":days[-1] if days else None,
            "model":scores["model"],"observed_features":scores["observed_features"],
            "by_venue":{v:_scores(rows) for v,rows in sorted(venues.items())},
            "earlier_dates":_scores([r for r in eligible if r["date"] in early]),
            "later_dates":_scores([r for r in eligible if r["date"] not in early]),
            "unranked_podium_races":sum(not set(r["result"]).issubset(
                {x["no"] for x in r["ranking"]}) for r in eligible),
            "method":"Same frozen cohort, strict T-15 timestamp consistency, unique race IDs; no refitting. Earlier/later dates are descriptive, not a prospective trial."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/auto/nar_predictions.json")
    parser.add_argument("--output", default="data/auto/nar_backtest.json")
    args = parser.parse_args()
    source = Path(args.input)
    if not source.exists():
        raise SystemExit("No historical prediction file; cannot claim a backtest result.")
    raw = source.read_text(encoding="utf-8").strip()
    if not raw:
        print("NAR historical prediction file is empty; zero records available.")
        payload = {"races": []}
    else:
        payload = json.loads(raw)
    records = payload.get("races", [])
    if not isinstance(records, list):
        raise SystemExit("Invalid race list")
    report = backtest(records)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

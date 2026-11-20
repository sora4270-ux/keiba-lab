#!/usr/bin/env python3
"""Audit frozen NAR forecasts; never backfill missing pre-decision odds."""
import argparse
import csv
import datetime as dt
import json
import math
from pathlib import Path

FIELDS = ("race_id", "horse_no", "decision_time", "odds_observed_time",
          "odds", "audit_status")


def audit(data):
    rows = []
    for record in data.get("races", []):
        rows.append(check(record))
    return rows


def check(record):
    row = {"race_id": record.get("id", ""), "horse_no": "",
           "decision_time": record.get("locked_at", ""),
           "odds_observed_time": "", "odds": "", "audit_status": "missing_data"}
    ranking = record.get("ranking") or []
    if not ranking or not isinstance(ranking[0], dict):
        return row
    row["horse_no"] = str(ranking[0].get("no", ""))
    snapshot = record.get("market_at_lock") or {}
    row["odds_observed_time"] = snapshot.get("updated_at", "")
    horses = snapshot.get("horses") or []
    for horse in horses:
        if str(horse.get("no")) == row["horse_no"]:
            row["odds"] = str(horse.get("odds") or "")
            break
    try:
        decision = dt.datetime.fromisoformat(row["decision_time"])
        observed = dt.datetime.fromisoformat(row["odds_observed_time"])
        cutoff = dt.datetime.fromisoformat(record["cutoff_at"])
        if not all(t.tzinfo is not None for t in (decision, observed, cutoff)):
            raise ValueError("naive timestamp")
        if not (observed <= decision < cutoff):
            row["audit_status"] = "invalid_temporal_order"
        elif decision - observed > dt.timedelta(minutes=15):
            row["audit_status"] = "stale_odds"
        elif not row["odds"] or not math.isfinite(float(row["odds"])) or float(row["odds"]) < 1:
            row["audit_status"] = "missing_odds"
        elif not row["race_id"].startswith("nar-") or not row["horse_no"]:
            row["audit_status"] = "invalid_identity"
        else:
            row["audit_status"] = "timestamp_checks_passed_not_authenticated"
    except (ValueError, KeyError, TypeError):
        row["audit_status"] = "missing_or_invalid_timestamps"
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/auto/nar_predictions.json")
    parser.add_argument("--output", default="nar-prelock-audit.csv")
    args = parser.parse_args()
    raw = Path(args.input).read_text(encoding="utf-8")
    if not raw.strip():
        parser.error("Frozen NAR prediction history is empty; no audit rows available")
    data = json.loads(raw)
    if not isinstance(data, dict) or not isinstance(data.get("races"), list):
        parser.error("Frozen NAR prediction history must contain a races list")
    rows = audit(data)
    with open(args.output, "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"records": len(rows),
                      "timestamp_checks_passed": sum(r["audit_status"] ==
                          "timestamp_checks_passed_not_authenticated" for r in rows),
                      "note": "Audit only. No fabricated grade, stake or odds; not an ROI bet file."}))


if __name__ == "__main__":
    main()

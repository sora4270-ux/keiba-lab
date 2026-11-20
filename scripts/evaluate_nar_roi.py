#!/usr/bin/env python3
"""Evaluate NAR win/place ROI from independently verified, timestamped bet rows.

Input CSV columns:
race_id,horse_no,grade,bet_type,stake_yen,official_payout_per_100_yen,
decision_time,odds_observed_time,odds,official_result_verified
Payout is the official amount per 100 yen stake, 0 for a verified losing bet.
Refunds/voids must be excluded upstream and documented separately.
"""
import argparse
import collections
import csv
import datetime as dt
import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

FIELDS = ("race_id", "horse_no", "grade", "bet_type", "stake_yen",
          "official_payout_per_100_yen", "decision_time", "odds_observed_time",
          "odds", "official_result_verified")
GRADES = ("S", "A", "B", "C")
TYPES = ("win", "place")


def evaluate(rows):
    grouped = collections.defaultdict(lambda: {"bets": 0, "stake_yen": Decimal(0),
                                                 "return_yen": Decimal(0)})
    rejected = collections.Counter()
    seen = set()
    for row in rows:
        try:
            if any(not str(row.get(k, "")).strip() for k in FIELDS):
                raise ValueError("missing_field")
            grade, kind = row["grade"], row["bet_type"]
            if grade not in GRADES or kind not in TYPES:
                raise ValueError("invalid_grade_or_bet_type")
            if row["official_result_verified"].strip().lower() != "true":
                raise ValueError("unverified_payout")
            stake = Decimal(row["stake_yen"])
            payout = Decimal(row["official_payout_per_100_yen"])
            odds = Decimal(row["odds"])
            if not all(v.is_finite() for v in (stake, payout, odds)):
                raise ValueError("nonfinite_number")
            if stake <= 0 or stake % 100 or payout < 0 or odds <= 0:
                raise ValueError("invalid_amount")
            decision = dt.datetime.fromisoformat(row["decision_time"])
            observed = dt.datetime.fromisoformat(row["odds_observed_time"])
            if decision.tzinfo is None or observed.tzinfo is None:
                raise ValueError("timezone_required")
            if observed > decision:
                raise ValueError("future_odds")
            key = (row["race_id"], row["horse_no"], kind)
            if key in seen:
                raise ValueError("duplicate_bet")
            seen.add(key)
            g = grouped[(grade, kind)]
            g["bets"] += 1
            g["stake_yen"] += stake
            g["return_yen"] += stake / Decimal(100) * payout
        except (ValueError, InvalidOperation, KeyError, TypeError) as exc:
            rejected[str(exc) or "invalid_row"] += 1
    output = {}
    for grade in GRADES:
        output[grade] = {}
        for kind in TYPES:
            g = grouped[(grade, kind)]
            stake = g["stake_yen"]
            output[grade][kind] = {
                "bets": g["bets"],
                "stake_yen": str(stake),
                "return_yen": str(g["return_yen"]),
                "roi_percent": str((g["return_yen"] / stake * 100).quantize(Decimal("0.01"))) if stake else None,
            }
    return {"status": "verified_rows_only", "by_grade": output,
            "accepted": sum(v["bets"] for v in grouped.values()),
            "rejected": dict(sorted(rejected.items())),
            "warning": "CSV verification flag is an assertion by data provider, not independently authenticated by this script. No refunds/voids modeled; do not infer profitability from small samples."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="nar-roi-report.json")
    args = parser.parse_args()
    with open(args.input, newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        if not reader.fieldnames or any(k not in reader.fieldnames for k in FIELDS):
            parser.error("Input CSV missing required columns")
        result = evaluate(reader)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

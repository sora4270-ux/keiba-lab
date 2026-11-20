#!/usr/bin/env python3
"""Join immutable pre-race selections with independently checked official payouts.

Predictions CSV columns:
race_id,horse_no,grade,bet_type,stake_yen,decision_time,odds_observed_time,odds
Payout CSV columns:
race_id,horse_no,bet_type,official_payout_per_100_yen,official_result_verified
Payout CSV MUST contain zero-payout rows for verified losers and must exclude
refunds, voids, dead heats and unsettled bets pending separate handling.
"""
import argparse
import collections
import csv
import json
from pathlib import Path
from evaluate_nar_roi import evaluate

PREDICTION_FIELDS = ("race_id", "horse_no", "grade", "bet_type", "stake_yen",
                     "decision_time", "odds_observed_time", "odds")
PAYOUT_FIELDS = ("race_id", "horse_no", "bet_type",
                 "official_payout_per_100_yen", "official_result_verified")


def reconcile(predictions, payouts):
    """Fail closed on ambiguous payout keys; never treat missing payout as loss."""
    payout_index = {}
    duplicate_keys = set()
    for p in payouts:
        if any(not str(p.get(k, "")).strip() for k in PAYOUT_FIELDS):
            continue
        key = tuple(p[k].strip() for k in ("race_id", "horse_no", "bet_type"))
        if key in payout_index:
            duplicate_keys.add(key)
        payout_index[key] = p
    selected = []
    reasons = collections.Counter()
    seen = set()
    for prediction in predictions:
        if any(not str(prediction.get(k, "")).strip() for k in PREDICTION_FIELDS):
            reasons["missing_prediction_field"] += 1
            continue
        key = tuple(prediction[k].strip() for k in ("race_id", "horse_no", "bet_type"))
        if key in seen:
            reasons["duplicate_prediction"] += 1
            continue
        seen.add(key)
        if key in duplicate_keys:
            reasons["ambiguous_payout"] += 1
            continue
        payout = payout_index.get(key)
        if payout is None:
            reasons["missing_payout"] += 1
            continue
        if payout["official_result_verified"].strip().lower() != "true":
            reasons["unverified_payout"] += 1
            continue
        selected.append({**prediction,
                         "official_payout_per_100_yen": payout["official_payout_per_100_yen"],
                         "official_result_verified": payout["official_result_verified"]})
    report = evaluate(selected)
    # A partial join can disproportionately exclude losing bets. Keep the
    # matched-sample result as diagnostic only until every prediction is
    # matched and passes validation.
    complete = len(predictions) > 0 and report["accepted"] == len(predictions)
    report["completeness"] = {
        "status": "complete_unverified_source" if complete else "incomplete_no_roi_claim",
        "predictions": len(predictions),
        "accepted": report["accepted"],
        "coverage_percent": round(100 * report["accepted"] / len(predictions), 2)
            if predictions else None,
        "source_authentication": "not_performed"
    }
    if not complete:
        report["matched_sample_by_grade"] = report["by_grade"]
        for grade_data in report["by_grade"].values():
            for bet_data in grade_data.values():
                bet_data["roi_percent"] = None
        report["status"] = "incomplete_no_roi_claim"
    report["reconciliation"] = {
        "predictions_seen": len(predictions),
        "payout_rows_seen": len(payouts),
        "matched_verified_candidates": len(selected),
        "excluded": dict(sorted(reasons.items())),
        "unmatched_payout_rows": sum(
            tuple(p.get(k, "").strip() for k in ("race_id", "horse_no", "bet_type")) not in seen
            for p in payouts),
        "warning": "No independent authentication of official payout source. Unmatched predictions are not losses."
    }
    return report


def load_csv(path, required):
    with open(path, newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames or any(k not in reader.fieldnames for k in required):
            raise ValueError(f"{path}: missing required columns")
        return list(reader)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--payouts", required=True)
    parser.add_argument("--output", default="nar-roi-reconciled.json")
    args = parser.parse_args()
    result = reconcile(load_csv(args.predictions, PREDICTION_FIELDS),
                       load_csv(args.payouts, PAYOUT_FIELDS))
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n",
                                 encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

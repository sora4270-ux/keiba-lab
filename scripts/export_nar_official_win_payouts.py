#!/usr/bin/env python3
"""Extract single-win payouts from official NAR monthly payback.csv.

Only races with a unique, valid win payout row are exported. A losing
selection gets zero ONLY when the race's official win market is verified.
Place is deliberately unsupported pending its column-spec verification.
"""
import argparse
import csv
import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlencode

from update_nar import BASE_URL, as_int, fetch_daily_zip, load_zip_tables, row_key


def official_win_market(tables):
    markets = {}
    conflicts = set()
    for item in tables.get("payback", []):
        key = row_key(item, ())
        if key is None:
            continue
        raw, _ = item
        no = as_int(raw[4]) if len(raw) > 5 else None
        amount = as_int(raw[5]) if len(raw) > 5 else None
        if no is None or not 1 <= no <= 30 or amount is None or not 100 <= amount <= 100000000:
            conflicts.add(key)
            continue
        existing = markets.setdefault(key, {})
        if no in existing and existing[no] != amount:
            conflicts.add(key)
        existing[no] = amount
    # Multiple win numbers can indicate dead heats. Defer these to a
    # settlement-aware evaluator rather than silently treating them as normal.
    return {key: payouts for key, payouts in markets.items()
            if key not in conflicts and len(payouts) == 1}


def extract(predictions, tables, expected_month=None):
    markets = official_win_market(tables)
    rows = []
    skipped = {}
    for p in predictions:
        if p.get("bet_type") != "win":
            skipped["unsupported_bet_type"] = skipped.get("unsupported_bet_type", 0) + 1
            continue
        race_id = p.get("race_id", "")
        # Exact canonical format: nar-YYYYMMDD-VENUE-RR
        if not race_id.startswith("nar-") or len(race_id.split("-")) != 4:
            skipped["noncanonical_race_id"] = skipped.get("noncanonical_race_id", 0) + 1
            continue
        _, day, venue, race_text = race_id.split("-")
        if len(day) != 8 or not day.isdigit() or not race_text.isdigit():
            skipped["noncanonical_race_id"] = skipped.get("noncanonical_race_id", 0) + 1
            continue
        if expected_month is not None and day[:6] != expected_month.replace("-", ""):
            skipped["outside_requested_month"] = skipped.get("outside_requested_month", 0) + 1
            continue
        market = markets.get((venue, day, int(race_text)))
        if market is None:
            skipped["missing_or_ambiguous_official_win_market"] = skipped.get("missing_or_ambiguous_official_win_market", 0) + 1
            continue
        no = as_int(p.get("horse_no"))
        if no is None or not 1 <= no <= 30:
            skipped["invalid_horse_number"] = skipped.get("invalid_horse_number", 0) + 1
            continue
        rows.append({"race_id": race_id, "horse_no": str(no), "bet_type": "win",
                     "official_payout_per_100_yen": str(market.get(no, 0)),
                     "official_result_verified": "true"})
    return rows, skipped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--predictions", required=True)
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--output", default="nar-official-win-payouts.csv")
    args = parser.parse_args()
    month = dt.date.fromisoformat(args.month + "-01")
    with open(args.predictions, newline="", encoding="utf-8-sig") as stream:
        predictions = list(csv.DictReader(stream))
    url = BASE_URL.split("?", 1)[0] + "?" + urlencode(
        {"type": "monthly", "k_year": month.year, "k_month": f"{month.month:02d}"})
    tables = load_zip_tables(fetch_daily_zip(url))
    if "payback" not in tables:
        parser.error("Official monthly archive does not include payback.csv")
    rows, skipped = extract(predictions, tables, expected_month=args.month)
    with open(args.output, "w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=("race_id", "horse_no", "bet_type",
                            "official_payout_per_100_yen", "official_result_verified"))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps({"source": "NAR official monthly payback.csv",
                      "month": args.month, "exported": len(rows), "skipped": skipped,
                      "caveat": "Single-win only; no dead heats/refunds/voids. Verify race completeness before ROI."},
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

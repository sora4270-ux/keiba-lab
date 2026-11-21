#!/usr/bin/env python3
"""Count pre-lock forecast and official win-payout join coverage, without ROI claims."""
import argparse
import collections
import csv
import json
from pathlib import Path

from export_nar_prelock_audit import audit
from export_nar_official_win_payouts import extract, official_win_market
from update_nar import BASE_URL, fetch_daily_zip, load_zip_tables
from urllib.parse import urlencode


def coverage(forecasts, tables, month):
    checked = audit(forecasts)
    selected = [{"race_id": r["race_id"], "horse_no": r["horse_no"],
                 "bet_type": "win"} for r in checked if r["race_id"]]
    official, skipped = extract(selected, tables, expected_month=month)
    payouts = {(r["race_id"], r["horse_no"]): r for r in official}
    counts = collections.Counter((r["race_id"], r["horse_no"]) for r in checked)
    statuses = collections.Counter()
    complete = 0
    for row in checked:
        if row["race_id"][4:10] != month.replace("-", ""):
            continue
        key = (row["race_id"], row["horse_no"])
        if counts[key] > 1:
            statuses["duplicate_frozen_selection"] += 1
        elif row["audit_status"] != "timestamp_checks_passed_not_authenticated":
            statuses["prelock_" + row["audit_status"]] += 1
        elif key not in payouts:
            statuses["official_payout_unavailable"] += 1
        else:
            statuses["both_present_source_not_authenticated"] += 1
            complete += 1
    total = sum(statuses.values())
    return {"month": month, "frozen_forecasts_checked": total,
            "both_present": complete,
            "coverage_percent": round(100 * complete / total, 2) if total else None,
            "by_status": dict(sorted(statuses.items())),
            "official_market_races": len(official_win_market(tables)),
            "payout_export_skipped": skipped,
            "roi_percent": None,
            "warning": "This is availability coverage, not authenticated ROI or a record of actual bets."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/auto/nar_predictions.json")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--output", default="nar-roi-coverage.json")
    args = parser.parse_args()
    if len(args.month) != 7 or args.month[4] != "-":
        parser.error("Month must be YYYY-MM")
    year, month = args.month.split("-")
    if not year.isdigit() or not month.isdigit() or not 1 <= int(month) <= 12:
        parser.error("Invalid month")
    raw = Path(args.input).read_text(encoding="utf-8")
    if not raw.strip():
        parser.error("Frozen NAR prediction history is empty; cannot audit coverage")
    forecasts = json.loads(raw)
    if not isinstance(forecasts, dict) or not isinstance(forecasts.get("races"), list):
        parser.error("Frozen NAR prediction history must contain a races list")
    url = BASE_URL.split("?", 1)[0] + "?" + urlencode(
        {"type": "monthly", "k_year": int(year), "k_month": month})
    tables = load_zip_tables(fetch_daily_zip(url))
    if "payback" not in tables:
        parser.error("Official archive lacks payback.csv")
    result = coverage(forecasts, tables, args.month)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

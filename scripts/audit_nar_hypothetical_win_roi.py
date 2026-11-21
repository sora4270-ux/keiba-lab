#!/usr/bin/env python3
"""Hypothetical 100-yen win-bet returns for auditable pre-lock NAR picks.

This is NOT actual betting history or a claim of verified bet placement.
"""
import argparse
import collections
import json
from pathlib import Path
from urllib.parse import urlencode

from export_nar_prelock_audit import audit
from export_nar_official_win_payouts import extract
from update_nar import BASE_URL, fetch_daily_zip, load_zip_tables


def simulate(forecasts, tables, month):
    checked = audit(forecasts)
    selected = [{"race_id": r["race_id"], "horse_no": r["horse_no"],
                 "bet_type": "win"} for r in checked if r["race_id"]]
    official, skipped = extract(selected, tables, expected_month=month)
    payouts = {(r["race_id"], r["horse_no"]): int(r["official_payout_per_100_yen"])
               for r in official if r["official_result_verified"] == "true"}
    duplicates = collections.Counter((r["race_id"], r["horse_no"]) for r in checked)
    excluded = collections.Counter()
    stake, returned, wins = 0, 0, 0
    month_prefix = "nar-" + month.replace("-", "")
    for row in checked:
        if not row["race_id"].startswith(month_prefix):
            continue
        key = (row["race_id"], row["horse_no"])
        if duplicates[key] > 1:
            excluded["duplicate_selection"] += 1
        elif row["audit_status"] != "timestamp_checks_passed_not_authenticated":
            excluded["prelock_" + row["audit_status"]] += 1
        elif key not in payouts:
            excluded["official_payout_unavailable"] += 1
        else:
            stake += 100
            returned += payouts[key]
            wins += payouts[key] > 0
    eligible = stake // 100
    return {"month": month, "eligible_races": eligible,
            "hypothetical_stake_yen": stake, "official_payout_sum_yen": returned,
            "winning_selections": wins,
            "hypothetical_win_rate_percent": round(wins / eligible * 100, 2) if eligible else None,
            "hypothetical_return_rate_percent": round(returned / stake * 100, 2) if stake else None,
            "hypothetical_profit_yen": returned - stake,
            "excluded": dict(sorted(excluded.items())),
            "payout_export_skipped": skipped,
            "warning": "Hypothetical 100-yen win bets on frozen top-ranked picks only. Not actual bets, authenticated betting records, or forward-looking expected returns."}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--month", required=True)
    parser.add_argument("--input", type=Path, default=Path("data/auto/nar_predictions.json"))
    parser.add_argument("--output", type=Path, default=Path("nar-win-hypothetical-roi.json"))
    args = parser.parse_args()
    try:
        year, month = args.month.split("-")
        if len(year) != 4 or len(month) != 2 or not 1 <= int(month) <= 12:
            raise ValueError()
    except ValueError:
        parser.error("month must be YYYY-MM")
    forecasts = json.loads(args.input.read_text(encoding="utf-8"))
    if not isinstance(forecasts, dict) or not isinstance(forecasts.get("races"), list):
        parser.error("invalid prediction history")
    url = BASE_URL.split("?", 1)[0] + "?" + urlencode(
        {"type": "monthly", "k_year": int(year), "k_month": month})
    tables = load_zip_tables(fetch_daily_zip(url))
    if "payback" not in tables:
        parser.error("official archive has no payback.csv")
    result = simulate(forecasts, tables, args.month)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Read-only equal-budget trio comparison with optional official payout checks."""
import argparse
from collections import Counter
from datetime import datetime, timedelta
from itertools import combinations
import json
from pathlib import Path

from audit_nar_daily_axes import _horse_numbers, _prelock
from backtest_nar_stake_allocation import official_market_index, official_settlement
from update_nar import load_zip_tables

STAKE_YEN = 1000


def strategies(ranking):
    if len(ranking) < 7:
        return None
    a = ranking
    return {
        "axis1": [tuple(sorted((a[0], *pair))) for pair in combinations(a[1:6], 2)],
        "axis2": [tuple(sorted((a[0], a[1], n))) for n in a[2:7]],
        "box5": [tuple(sorted(t)) for t in combinations(a[:5], 3)],
    }


def analyze(records, date=None, official_tables=None):
    if not isinstance(records, list):
        raise ValueError("races must be a list")
    exclusions = Counter()
    hits = Counter()
    matched = 0
    seen = set()
    by_day = {}
    market = official_market_index(official_tables) if official_tables is not None else None
    paid = Counter()
    payout_verified = 0
    payout_excluded = Counter()
    for r in records:
        if not isinstance(r, dict) or (date and r.get("date") != date):
            continue
        key = r.get("id")
        if not isinstance(key, str) or not key or key in seen:
            exclusions["duplicate_or_missing_id"] += 1
            continue
        seen.add(key)
        if r.get("status") == "draft" or r.get("result_alternatives"):
            exclusions["draft_or_dead_heat"] += 1
            continue
        result = _horse_numbers(r.get("result"))
        ranking = _horse_numbers(r.get("ranking"))
        if result is None or len(result) != 3:
            exclusions["invalid_result"] += 1
            continue
        if ranking is None or len(ranking) < 7:
            exclusions["fewer_than_seven_ranked"] += 1
            continue
        if not _prelock(r):
            exclusions["unverifiable_lock"] += 1
            continue
        picks = strategies(ranking)
        target = tuple(sorted(result))
        day = r.get("date")
        if not isinstance(day, str):
            exclusions["missing_date"] += 1
            continue
        matched += 1
        official = None
        if market is not None:
            official, error = official_settlement(r, market)
            if error:
                payout_excluded[error] += 1
            else:
                payout_verified += 1
        if day not in by_day:
            by_day[day] = {"races": 0, "hits": {name: 0 for name in picks}}
        by_day[day]["races"] += 1
        for name, tickets in picks.items():
            if target in tickets:
                hits[name] += 1
                if official is not None:
                    paid[name] += official["payouts"]["trio"] * (STAKE_YEN // len(tickets)) // 100
                by_day[day]["hits"][name] += 1
    return {
        "date": date or "all",
        "status": "retrospective_saved_forecasts_not_independently_authenticated",
        "eligible_races": matched,
        "excluded": dict(sorted(exclusions.items())),
        "stake_per_race_per_strategy_yen": STAKE_YEN,
        "strategies": {
            name: {
                "tickets": count,
                "yen_per_ticket": STAKE_YEN // count,
                "hypothetical_total_stake_yen": matched * STAKE_YEN,
                "hits": hits[name],
                "hit_rate_percent": round(hits[name] * 100 / matched, 2) if matched else None,
            }
            for name, count in (("axis1", 10), ("axis2", 5), ("box5", 10))
        },
        "by_day": dict(sorted(by_day.items())),
        "official_settlement": {
            "status": ("not_supplied" if market is None else
                       "official_payouts_unavailable" if not payout_verified else
                       "official_payouts_partially_reconciled_prelock_not_authenticated" if payout_verified < matched else
                       "official_payouts_reconciled_prelock_not_authenticated"),
            "verified_races": payout_verified,
            "excluded": dict(sorted(payout_excluded.items())),
            "per_strategy": {
                name: {
                    "stake_yen": payout_verified * STAKE_YEN,
                    "payout_yen": paid[name],
                    "net_yen": paid[name] - payout_verified * STAKE_YEN,
                    "roi_percent": round(paid[name] * 100 / (payout_verified * STAKE_YEN), 2) if payout_verified else None,
                }
                for name in ("axis1", "axis2", "box5")
            },
        },
        "notes": [
            "All methods use the same races and hypothetical 1000 yen each per race.",
            "Axis1: #1 fixed + 2 of ranks #2-#6 (10 tickets x 100 yen).",
            "Axis2: #1 and #2 fixed + 1 of ranks #3-#7 (5 tickets x 200 yen).",
            "Box5: ranks #1-#5 (10 tickets x 100 yen).",
            "ROI is shown only on the common subset of races independently joined to official payout rows; never mix with the full hit-rate denominator.",
            "Frozen timestamps are consistency checks, not independent pre-race proof.",
            "No production betting policy, rankings, records, or real wagers are changed.",
        ],
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input", type=Path, default=Path("data/auto/nar_predictions.json"))
    p.add_argument("--date", default=None)
    p.add_argument("--official-zip", type=Path, default=None)
    p.add_argument("--output", type=Path, default=Path("nar-trio-strategy-audit.json"))
    args = p.parse_args()
    if args.date and datetime.strptime(args.date, "%Y-%m-%d").strftime("%Y-%m-%d") != args.date:
        p.error("invalid date")
    raw = json.loads(args.input.read_text(encoding="utf-8"))
    tables = load_zip_tables(args.official_zip.read_bytes()) if args.official_zip else None
    if tables is not None and "payback" not in tables:
        p.error("Official ZIP is missing payback.csv")
    result = analyze(raw["races"], args.date, tables)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

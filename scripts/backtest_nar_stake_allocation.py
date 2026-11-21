#!/usr/bin/env python3
"""Read-only paired historical stake-allocation diagnostics on frozen NAR picks.

Same cohort and same fixed 5,000 JPY hypothetical stake for EVERY allocation.
Payouts are stored official-CSV-derived claims, NOT independently reauthenticated.
No real bets, outcome-based ticket selection, or future feature refitting.
"""
import argparse
import collections
import datetime as dt
import itertools
import json
from pathlib import Path

TICKET_UNITS = 50
# Fixed ex ante alternatives, no fitting to winning outcomes.
PLANS = {
    "balanced": {"win": 10, "wide": 10, "trio": 10, "trifecta": 20},
    "no_trifecta": {"win": 20, "wide": 20, "trio": 10, "trifecta": 0},
    "wide_focus": {"win": 10, "wide": 30, "trio": 10, "trifecta": 0},
    "trio_focus": {"win": 10, "wide": 10, "trio": 30, "trifecta": 0},
    "trifecta_focus": {"win": 5, "wide": 5, "trio": 10, "trifecta": 30},
}


def valid_ticket(value, size, ordered):
    if not isinstance(value, list) or len(value) != size:
        return None
    if any(type(n) is not int or n < 1 or n > 30 for n in value) or len(set(value)) != size:
        return None
    return tuple(value) if ordered else tuple(sorted(value))


def eligible(r):
    if not isinstance(r, dict) or r.get("status") == "draft" or r.get("result_alternatives"):
        return None, "unsettled_or_dead_heat"
    try:
        start = dt.datetime.fromisoformat(r["start_at"])
        cutoff = dt.datetime.fromisoformat(r["cutoff_at"])
        lock = dt.datetime.fromisoformat(r["locked_at"])
        predicted = dt.datetime.fromisoformat(r["predicted_at"])
        if not all(v.tzinfo is not None for v in (start, cutoff, lock, predicted)):
            return None, "naive_timestamp"
        if not (predicted <= lock <= cutoff == start - dt.timedelta(minutes=15)):
            return None, "late_or_inconsistent_lock"
        result = valid_ticket(r["result"], 3, True)
        ranked = r["ranking"]
        nos = [x["no"] for x in ranked]
        if not result or len(nos) < 5 or len(nos) != len(set(nos)) or any(type(n) is not int or n < 1 for n in nos):
            return None, "invalid_ranking_or_result"
        if not set(result).issubset(nos):
            return None, "result_not_in_field"
        trio = [valid_ticket(t, 3, False) for t in r["trio_tickets"]]
        trifecta = [valid_ticket(t, 3, True) for t in r["tickets"]]
        if not trio or not trifecta or None in trio or None in trifecta:
            return None, "missing_or_invalid_frozen_tickets"
        if len(set(trio)) != len(trio) or len(set(trifecta)) != len(trifecta):
            return None, "duplicate_tickets"
        actual_pairs = set(itertools.combinations(sorted(result), 2))
        wide = r["wide_payouts"]
        amounts = r["payouts"]
        if not isinstance(wide, dict) or not isinstance(amounts, dict):
            return None, "unverified_settlement"
        payout = {}
        for kind in ("win", "trio", "trifecta"):
            v = amounts.get(kind)
            if type(v) is not int or not 100 <= v <= 100000000:
                return None, "missing_official_payout"
            payout[kind] = v
        wide_paid = {}
        for pair in actual_pairs:
            key = "-".join(map(str, pair))
            v = wide.get(key)
            if type(v) is not int or not 100 <= v <= 100000000:
                return None, "missing_wide_market"
            wide_paid[pair] = v
        tickets = {
            "win": [(nos[0],)],
            "wide": list(itertools.combinations(sorted(nos[:5]), 2)),
            "trio": trio,
            "trifecta": trifecta,
        }
        # A winning payout must agree with settled result, not just an arbitrary ticket.
        winning = {
            "win": (result[0],),
            "trio": tuple(sorted(result)),
            "trifecta": result,
        }
        return {"tickets": tickets, "winning": winning, "wide": wide_paid, "payout": payout}, None
    except (KeyError, TypeError, ValueError, AttributeError):
        return None, "missing_or_malformed_record"


def settle_one(info, plan):
    spent = paid = 0
    by_type = {}
    for kind, units in plan.items():
        tickets = info["tickets"][kind]
        assert tickets and units >= 0
        each, remaining = divmod(units, len(tickets))
        stakes = [100 * (each + (i < remaining)) for i in range(len(tickets))]
        stake = sum(stakes)
        returned = 0
        for ticket, money in zip(tickets, stakes):
            if not money:
                continue
            if kind == "wide":
                award = info["wide"].get(ticket, 0)
            else:
                award = info["payout"][kind] if ticket == info["winning"][kind] else 0
            returned += money // 100 * award
        by_type[kind] = {"stake_yen": stake, "payout_yen": returned}
        spent += stake
        paid += returned
    assert spent == TICKET_UNITS * 100, "fixed-budget parity violated"
    return spent, paid, by_type


def metrics(rows):
    stake, paid = 0, 0
    peak = equity = drawdown = 0
    by_type = {k: {"stake_yen": 0, "payout_yen": 0} for k in ("win", "wide", "trio", "trifecta")}
    for spent, returned, subs in rows:
        stake += spent
        paid += returned
        equity += returned - spent
        peak = max(peak, equity)
        drawdown = max(drawdown, peak-equity)
        for k, v in subs.items():
            by_type[k]["stake_yen"] += v["stake_yen"]
            by_type[k]["payout_yen"] += v["payout_yen"]
    for v in by_type.values():
        v["roi_percent"] = round(100*v["payout_yen"]/v["stake_yen"], 2) if v["stake_yen"] else None
    return {"races": len(rows), "stake_yen": stake, "payout_yen": paid,
            "net_yen": paid-stake, "roi_percent": round(100*paid/stake, 2) if stake else None,
            "max_drawdown_yen": drawdown, "by_type": by_type}


def backtest(records, month=None):
    skipped = collections.Counter()
    accepted = []
    ids = set()
    for r in records:
        if month and (not isinstance(r, dict) or not str(r.get("date", "")).startswith(month)):
            continue
        info, reason = eligible(r)
        if reason:
            skipped[reason] += 1
            continue
        key = r.get("id")
        if not isinstance(key, str) or not key or key in ids:
            skipped["duplicate_or_missing_race_id"] += 1
            continue
        ids.add(key)
        accepted.append((r, info))
    accepted.sort(key=lambda x: (x[0]["date"], x[0]["start_at"], x[0]["id"]))
    dates = sorted({r["date"] for r, _ in accepted})
    # A time split with no test days must not be portrayed as out-of-sample.
    n_train = max(1, int(len(dates)*.7)) if len(dates) > 1 else len(dates)
    train_dates = set(dates[:n_train])
    out = {"status": "saved_payouts_unverified_external_reconciliation",
           "month": month or "all", "eligible_races": len(accepted), "excluded": dict(sorted(skipped.items())),
           "stake_per_race_yen": TICKET_UNITS*100,
           "train_dates": len(train_dates), "holdout_dates": len(dates)-len(train_dates),
           "plans": {}, "by_course_type": {}}
    for name, plan in PLANS.items():
        assert sum(plan.values()) == TICKET_UNITS
        cohort = [(r, settle_one(info, plan)) for r, info in accepted]
        out["plans"][name] = {
            "allocation_units_100yen": plan,
            "all": metrics([value for _, value in cohort]),
            "earlier_dates": metrics([value for r, value in cohort if r["date"] in train_dates]),
            "later_unseen_dates": metrics([value for r, value in cohort if r["date"] not in train_dates]),
        }
        for category in ("banei", "flat"):
            subset = [value for r, value in cohort
                      if ("帯広" in r.get("venue", "") or "ばんえい" in r.get("venue", "")) == (category == "banei")]
            out["by_course_type"].setdefault(category, {})[name] = metrics(subset)
    out["notes"] = [
        "Historical diagnostic only. Not real wagers and not independently reauthenticated official payouts.",
        "All allocations use the same qualified races and identical 5000-yen budget.",
        "Ticket order and ranking are saved before start; late/future and dead-heat records are excluded.",
        "When a type budget cannot cover every frozen ticket, only its earliest saved tickets are hypothetically staked.",
        "No optimization, approval for automatic betting, or claim of future positive return.",
    ]
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/auto/nar_predictions.json"))
    parser.add_argument("--month", default=None)
    parser.add_argument("--output", type=Path, default=Path("nar-stake-backtest.json"))
    a = parser.parse_args()
    raw = json.loads(a.input.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("races"), list):
        parser.error("Input must have races array")
    result = backtest(raw["races"], a.month)
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("plans", "by_course_type")}, ensure_ascii=False))
    for name, values in result["plans"].items():
        print(name, json.dumps(values["all"], ensure_ascii=False))


if __name__ == "__main__":
    main()

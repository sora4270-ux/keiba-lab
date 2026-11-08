#!/usr/bin/env python3
"""Experimental, *pre-race* value-and-coverage selector for NAR.

This is a shadow strategy: it never changes the existing saved bets and never
places wagers. Its model probabilities are hypotheses, NOT calibrated odds.
"""
import datetime as dt
import math

MIN_TICKETS = 4
MAX_TICKETS = 10
TICKET_BUCKETS = (4, 6, 8, 10)


def build_shadow_plan(ranking, ordered, trios, official_trio_odds, observed_at,
                      has_win_market, win_market_observed_at=None,
                      target_mass=0.75, minimum_multiple=1.15, stress_factor=0.85):
    """Choose the smallest 5..7 horse set meeting unconditional trio coverage.

    All probabilities and quotes must be observed before the forecast lock.
    Missing odds lead to a genuine zero-ticket decision, not estimated prices.
    """
    if not 0 < target_mass <= 1 or not 0 < stress_factor <= 1 or minimum_multiple < 1:
        raise ValueError("Invalid experimental thresholds")
    ids = [int(h["no"]) for h in ranking]
    if len(ids) < 3 or len(ids) != len(set(ids)):
        raise ValueError("Invalid ranked horse list")
    coverage = {}
    for n in range(min(7, len(ids)), 4, -1):
        group = set(ids[:n])
        coverage[n] = sum(float(p) for ticket, p in trios
                          if len(ticket) == 3 and len(set(ticket)) == 3
                          and set(ticket).issubset(group)
                          and math.isfinite(float(p)) and p > 0)
    candidate_count = next((n for n in (5, 6, 7) if coverage.get(n, 0) >= target_mass), None)
    result = {
        "policy": "value_coverage_shadow_v1",
        "status": "below_coverage",
        "reason": "上位7頭までの3着独占確率が暫定目標に届かないため見送り",
        "target_mass": target_mass,
        "coverage_by_count": {str(k): round(v, 6) for k, v in sorted(coverage.items())},
        "candidate_count": candidate_count,
        "candidate_horses": ids[:candidate_count] if candidate_count else [],
        "win_market_required": True,
        "minimum_multiple": minimum_multiple,
        "stress_factor": stress_factor,
        "observed_at": observed_at,
        "quote_count": len(official_trio_odds) if isinstance(official_trio_odds, dict) else 0,
        "tickets": [],
        "count": 0,
        "stake_yen": 0,
        "estimated_hit_probability": 0.,
        "stress_expected_return_multiple": None,
    }
    if candidate_count is None:
        return result

    def skip(code, reason):
        result["status"] = code
        result["reason"] = reason
        return result

    if not has_win_market:
        return skip("no_win_market", "単勝の全頭オッズがそろっていないため見送り")
    try:
        run = dt.datetime.fromisoformat(observed_at)
        market = dt.datetime.fromisoformat(win_market_observed_at or observed_at)
        if run.tzinfo is None or market.tzinfo is None or market > run:
            return skip("stale_market", "単勝オッズの取得時刻が確認できないため見送り")
        if run - market > dt.timedelta(minutes=15):
            return skip("stale_market", "単勝オッズが15分より古いため見送り")
    except (ValueError, TypeError):
        return skip("stale_market", "単勝オッズの取得時刻が不正なため見送り")
    if not official_trio_odds:
        return skip("no_trio_quotes", "発走前の公式3連複オッズが未取得のため見送り")

    candidates = set(ids[:candidate_count])
    viable = []
    matched = 0
    for ticket, probability in trios:
        if len(ticket) != 3 or not set(ticket).issubset(candidates):
            continue
        key = tuple(sorted(int(n) for n in ticket))
        price = official_trio_odds.get(key)
        if not isinstance(price, (int, float)) or not math.isfinite(price) or price < 1:
            continue
        matched += 1
        p = float(probability)
        if not math.isfinite(p) or p <= 0:
            continue
        multiple = stress_factor * p * float(price)
        if multiple >= minimum_multiple:
            viable.append((p * (multiple - 1), p, multiple, key, float(price)))
    result["matched_quotes"] = matched
    if not matched:
        return skip("no_matching_quotes", "候補の公式3連複オッズが未取得のため見送り")
    if len(viable) < MIN_TICKETS:
        return skip("below_value", "保守的な期待値基準を満たす候補が4点未満のため見送り")

    viable.sort(key=lambda x: (-x[0], -x[1], x[3]))
    size = max(n for n in TICKET_BUCKETS if n <= min(len(viable), MAX_TICKETS))
    selected = viable[:size]
    result.update(
        status="experimental_candidate",
        reason="発走前の公式3連複オッズと暫定的な確率補正で選んだ検証用買い目",
        tickets=[list(row[3]) for row in selected],
        count=size,
        stake_yen=size * 100,
        estimated_hit_probability=round(sum(row[1] for row in selected), 6),
        stress_expected_return_multiple=round(sum(row[2] for row in selected) / size, 3),
    )
    return result

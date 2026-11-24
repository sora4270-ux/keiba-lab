#!/usr/bin/env python3
"""Read-only daily audit of frozen NAR axes and combination misses.

All metrics are retrospective diagnostics, NOT a pre-race betting policy.
Never rewrites rankings, odds, tickets, results or the frozen ledger.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
from pathlib import Path
from zoneinfo import ZoneInfo


def _horse_numbers(rows):
    if not isinstance(rows, list):
        return None
    out = []
    for row in rows:
        number = row.get("no") if isinstance(row, dict) else row
        if type(number) is not int or not 1 <= number <= 30:
            return None
        out.append(number)
    return out if len(set(out)) == len(out) else None


def _prelock(record):
    try:
        start, cutoff, locked, predicted = (
            datetime.fromisoformat(record[name])
            for name in ("start_at", "cutoff_at", "locked_at", "predicted_at")
        )
        return (all(t.tzinfo is not None for t in (start, cutoff, locked, predicted))
                and predicted <= locked < cutoff
                and cutoff == start - timedelta(minutes=15))
    except (KeyError, TypeError, ValueError):
        return False


def _ticket_result(record, field, result, ordered):
    raw = record.get(field)
    if not isinstance(raw, list) or not raw:
        return "unrecorded"
    tickets = [_horse_numbers(row) for row in raw]
    if any(row is None or len(row) != 3 for row in tickets):
        return "unrecorded"
    winning = tuple(result) if ordered else tuple(sorted(result))
    combos = [tuple(row) if ordered else tuple(sorted(row)) for row in tickets]
    # Duplicate frozen tickets are malformed evidence, never extra hits.
    if len(set(combos)) != len(combos):
        return "unrecorded"
    if winning in combos:
        return "hit"
    candidates = {n for row in tickets for n in row}
    if not set(result).issubset(candidates):
        return "candidate_missing"
    if ordered and tuple(sorted(result)) in [tuple(sorted(row)) for row in tickets]:
        return "order_mismatch"
    return "combination_missing"


def analyze(records, race_date):
    if not isinstance(records, list):
        raise ValueError("races must be a list")
    counted = Counter()
    excluded = Counter()
    trio = Counter()
    trifecta = Counter()
    venues = defaultdict(Counter)
    winner_ranks = Counter()
    quality_alerts = Counter()
    race_reviews = []
    # Identical duplicates can be counted once; conflicting duplicates must
    # never contribute a hit or miss based on arbitrary input order.
    first_by_id = {}
    conflicting_ids = set()
    for record in records:
        if not isinstance(record, dict) or record.get("date") != race_date:
            continue
        race_id = record.get("id")
        if not isinstance(race_id, str) or not race_id:
            continue
        if race_id in first_by_id and first_by_id[race_id] != record:
            conflicting_ids.add(race_id)
        else:
            first_by_id[race_id] = record
    seen = set()
    examined = 0
    race_details = []
    disciplines = defaultdict(Counter)
    for record in records:
        if not isinstance(record, dict) or record.get("date") != race_date:
            continue
        examined += 1
        race_id = record.get("id")
        if isinstance(race_id, str) and race_id in conflicting_ids:
            excluded["conflicting_duplicate_id"] += 1
            continue
        if not isinstance(race_id, str) or not race_id or race_id in seen:
            excluded["missing_or_duplicate_id"] += 1
            continue
        seen.add(race_id)
        if record.get("status") == "draft" or record.get("result_alternatives"):
            excluded["draft_or_dead_heat"] += 1
            continue
        result = _horse_numbers(record.get("result"))
        ranking = _horse_numbers(record.get("ranking"))
        if result is None or len(result) != 3:
            excluded["missing_or_invalid_result"] += 1
            continue
        if ranking is None or len(ranking) < 5:
            excluded["missing_or_invalid_ranking"] += 1
            continue
        if not _prelock(record):
            excluded["prelock_not_verifiable"] += 1
            continue
        venue = str(record.get("venue") or "不明")
        discipline = "banei" if venue == "帯広ば" else "flat"
        diagnostics = {
            "top1_win": ranking[0] == result[0],
            "top1_in_podium": ranking[0] in result,
            "top2_both_in_podium": set(ranking[:2]).issubset(result),
            "podium_inside_top5": set(result).issubset(ranking[:5]),
            "winner_outside_top5": result[0] not in ranking[:5],
            "podium_horse_outside_ranking": not set(result).issubset(ranking),
        }
        ticket_diagnostics = {
            "trio": _ticket_result(record, "trio_tickets", result, False),
            "trifecta": _ticket_result(record, "tickets", result, True),
        }
        race_details.append({"id": race_id, "venue": venue, "discipline": discipline,
                             "ranking": ranking, "result": result,
                             **diagnostics, **ticket_diagnostics})
        disciplines[discipline]["settled"] += 1
        for metric, success in diagnostics.items():
            disciplines[discipline][metric] += int(success)
        for kind, reason in ticket_diagnostics.items():
            venues[venue][f"{kind}_{reason}"] += 1
            disciplines[discipline][f"{kind}_{reason}"] += 1
        # Existing venue counters below already cover the other metrics.
        venues[venue]["top1_in_podium"] += int(diagnostics["top1_in_podium"])
        venues[venue]["winner_outside_top5"] += int(diagnostics["winner_outside_top5"])
        counted["settled"] += 1
        venues[venue]["settled"] += 1
        winning_rank = ranking.index(result[0]) + 1 if result[0] in ranking else None
        bucket = (str(winning_rank) if winning_rank <= 5 else "6plus") if winning_rank else "not_in_ranking"
        winner_ranks[bucket] += 1
        venues[venue]["winner_rank_" + bucket] += 1
        # This is a completeness flag, NOT proof of scratch/withdrawal.
        # Some official finish-order snapshots can be incomplete.
        missing_from_finish_order = []
        finish_order = _horse_numbers(record.get("finish_order"))
        if finish_order is not None and len(finish_order) >= 3 and set(result).issubset(finish_order):
            missing_from_finish_order = sorted(set(ranking) - set(finish_order))
            if missing_from_finish_order:
                quality_alerts["ranked_horses_absent_from_finish_order"] += 1
        if ranking[0] == result[0]:
            counted["top1_win"] += 1
            venues[venue]["top1_win"] += 1
        if ranking[0] in result:
            counted["top1_in_podium"] += 1
        if set(ranking[:2]).issubset(result):
            counted["top2_both_in_podium"] += 1
            venues[venue]["top2_both_in_podium"] += 1
        if set(result).issubset(ranking[:5]):
            counted["podium_inside_top5"] += 1
            venues[venue]["podium_inside_top5"] += 1
        if not set(result).issubset(ranking):
            counted["podium_horse_outside_ranking"] += 1
            venues[venue]["podium_horse_outside_ranking"] += 1
        if result[0] not in ranking[:5]:
            counted["winner_outside_top5"] += 1
        ticket_states = {}
        for field, scores, ordered in (
            ("trio_tickets", trio, False),
            ("tickets", trifecta, True),
        ):
            outcome = _ticket_result(record, field, result, ordered)
            scores[outcome] += 1
            ticket_states[field] = outcome
        if (winning_rank is None or winning_rank > 5
                or any(outcome != "hit" for outcome in ticket_states.values())
                or missing_from_finish_order):
            race_reviews.append({
                "id": race_id, "venue": venue, "race_no": record.get("race_no"),
                "result": result, "frozen_top5": ranking[:5],
                "winner_predicted_rank": winning_rank,
                "trio_reason": ticket_states["trio_tickets"],
                "trifecta_reason": ticket_states["tickets"],
                "ranked_horses_absent_from_finish_order": missing_from_finish_order,
            })
    race_reviews.sort(key=lambda item: (item["venue"], item["race_no"] or 0, item["id"]))
    return {
        "date": race_date,
        "status": "retrospective_saved_forecasts_not_independently_authenticated",
        "races_on_date": examined,
        "settled_eligible": counted["settled"],
        "excluded": dict(sorted(excluded.items())),
        "top1_win": counted["top1_win"],
        "top1_in_podium": counted["top1_in_podium"],
        "top2_both_in_podium": counted["top2_both_in_podium"],
        "podium_inside_top5": counted["podium_inside_top5"],
        "winner_outside_top5": counted["winner_outside_top5"],
        "winner_predicted_rank_distribution": dict(sorted(winner_ranks.items())),
        "finish_order_quality_flags": dict(sorted(quality_alerts.items())),
        "race_reviews": race_reviews,
        "podium_horse_outside_ranking": counted["podium_horse_outside_ranking"],
        "trio": {k: trio[k] for k in ("hit", "candidate_missing", "combination_missing", "unrecorded")},
        "trifecta": {k: trifecta[k] for k in ("hit", "candidate_missing", "order_mismatch", "combination_missing", "unrecorded")},
        "venues": {k: dict(sorted(v.items())) for k, v in sorted(venues.items())},
        "disciplines": {k: dict(sorted(v.items())) for k, v in sorted(disciplines.items())},
        "race_details": race_details,
        "notes": [
            "Historical top-2 podium inclusion is NOT evidence of future 2-axis profitability.",
            "Saved timestamps are consistency checks only, not independently authenticated pre-race proof.",
            "Ticket counts and returns are NOT inferred; no betting occurred in this audit.",
            "Results are excluded where dead heat, missing data, or T-15 consistency prevent fair evaluation.",
            "A podium finisher absent from the frozen ranking is counted as a miss, never dropped from the denominator.",
            "Race reviews classify prediction misses; they do not prove official payouts or financial returns.",
            "A ranked runner missing from stored finish_order requires manual official confirmation; it is NOT automatically a scratch, refund or losing bet.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/auto/nar_predictions.json"))
    parser.add_argument("--date", default=datetime.now(ZoneInfo("Asia/Tokyo")).date().isoformat())
    parser.add_argument("--output", type=Path, default=Path("nar-daily-axes.json"))
    args = parser.parse_args()
    if datetime.strptime(args.date, "%Y-%m-%d").date().isoformat() != args.date:
        parser.error("date must be YYYY-MM-DD")
    data = json.loads(args.input.read_text(encoding="utf-8"))
    report = analyze(data["races"], args.date)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()

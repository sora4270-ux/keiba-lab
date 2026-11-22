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
    seen = set()
    examined = 0
    for record in records:
        if not isinstance(record, dict) or record.get("date") != race_date:
            continue
        examined += 1
        race_id = record.get("id")
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
        if ranking is None or len(ranking) < 5 or not set(result).issubset(ranking):
            excluded["missing_or_invalid_ranking"] += 1
            continue
        if not _prelock(record):
            excluded["prelock_not_verifiable"] += 1
            continue
        venue = str(record.get("venue") or "不明")
        counted["settled"] += 1
        venues[venue]["settled"] += 1
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
        if result[0] not in ranking[:5]:
            counted["winner_outside_top5"] += 1
        for field, scores, ordered in (
            ("trio_tickets", trio, False),
            ("tickets", trifecta, True),
        ):
            scores[_ticket_result(record, field, result, ordered)] += 1
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
        "trio": {k: trio[k] for k in ("hit", "candidate_missing", "combination_missing", "unrecorded")},
        "trifecta": {k: trifecta[k] for k in ("hit", "candidate_missing", "order_mismatch", "combination_missing", "unrecorded")},
        "venues": {k: dict(sorted(v.items())) for k, v in sorted(venues.items())},
        "notes": [
            "Historical top-2 podium inclusion is NOT evidence of future 2-axis profitability.",
            "Saved timestamps are consistency checks only, not independently authenticated pre-race proof.",
            "Ticket counts and returns are NOT inferred; no betting occurred in this audit.",
            "Results are excluded where dead heat, missing data, or T-15 consistency prevent fair evaluation.",
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

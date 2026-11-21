#!/usr/bin/env python3
"""Read-only historical evaluation of frozen NAR ranked picks, not betting ROI."""
import argparse
import json
from pathlib import Path

MARKS = ("◎", "○", "▲", "△", "☆")


def evaluate(data):
    races = data.get("races")
    if not isinstance(races, list):
        raise ValueError("Forecast history must have a races list")
    stats = [{"mark": mark, "eligible": 0, "wins": 0, "top3": 0}
             for mark in MARKS]
    settled = 0
    skipped = 0
    for race in races:
        if not isinstance(race, dict):
            skipped += 1
            continue
        ranking, result = race.get("ranking"), race.get("result")
        # Ambiguous dead heats have multiple valid finish orders; exclude them
        # rather than assigning a potentially false single winner.
        alternatives = race.get("result_alternatives") or []
        if alternatives:
            if not isinstance(alternatives, list) or len(alternatives) != 1:
                skipped += 1
                continue
            try:
                alternative = [int(no) for no in alternatives[0][:3]]
                primary = [int(no) for no in result[:3]]
            except (TypeError, ValueError, IndexError):
                skipped += 1
                continue
            if alternative != primary:
                skipped += 1
                continue
        if (not isinstance(ranking, list) or not isinstance(result, list)
                or len(result) < 3 or len(set(map(str, result[:3]))) != 3):
            skipped += 1
            continue
        try:
            podium = [int(no) for no in result[:3]]
        except (ValueError, TypeError):
            skipped += 1
            continue
        if any(no <= 0 for no in podium):
            skipped += 1
            continue
        # A corrupt or duplicated saved selection must not inflate hit rates.
        picks = []
        for entry in ranking[:5]:
            if not isinstance(entry, dict):
                picks.append(None)
                continue
            try:
                horse = int(entry["no"])
                picks.append(horse if horse > 0 else None)
            except (KeyError, ValueError, TypeError):
                picks.append(None)
        if len([no for no in picks if no is not None]) != len(set(no for no in picks if no is not None)):
            skipped += 1
            continue
        settled += 1
        for i, horse in enumerate(picks):
            if horse is None:
                continue
            row = stats[i]
            row["eligible"] += 1
            row["wins"] += horse == podium[0]
            row["top3"] += horse in podium
    for row in stats:
        count = row["eligible"]
        row["win_rate_percent"] = round(100 * row["wins"] / count, 2) if count else None
        row["top3_rate_percent"] = round(100 * row["top3"] / count, 2) if count else None
    return {
        "frozen_forecasts": len(races), "settled_with_valid_result": settled,
        "skipped_unsettled_or_invalid": skipped, "by_rank_mark": stats,
        "roi_percent": None,
        "note": "Marks represent saved ranking positions (◎○▲△☆), not separately authenticated marks. Rates are descriptive; no odds, stakes, or ROI inferred."
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("data/auto/nar_predictions.json"))
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.input.read_text(encoding="utf-8"))
    report = evaluate(data)
    serialized = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(serialized, encoding="utf-8")
    print(serialized, end="")


if __name__ == "__main__":
    main()

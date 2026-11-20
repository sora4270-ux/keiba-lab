#!/usr/bin/env python3
"""Historical NAR replay from official monthly results, with strict prior-day cutoffs.

This is a historical recent-form-only diagnostic. Monthly CSV cumulative
career/distance/jockey stats are NOT used: they can contain post-race information.
"""
import argparse
import collections
import datetime as dt
import json
from pathlib import Path
from urllib.parse import urlencode

from recent_form import LOOKBACK_DAYS, features_on, history_runs, horse_key
from update_nar import BASE_URL, fetch_daily_zip, load_zip_tables, row_key, cell, as_int


def replay(monthly_tables, start, end, max_races=1000):
    """Only results dated strictly earlier than each target day are features."""
    race_rows = {}
    horse_rows = collections.defaultdict(list)
    for tables in monthly_tables:
        for item in tables["racelist"]:
            key = row_key(item, ())
            if key:
                race_rows[key] = item
        for item in tables["horselist"]:
            key = row_key(item, ())
            if key:
                horse_rows[key].append(item)
    keys = sorted((k for k in race_rows if start <= k[1] <= end), key=lambda k: (k[1], k[0], k[2]))
    keys = keys[:max_races]
    history = {}
    # Historical form extraction processes only races strictly before each target date.
    # history_runs is invoked on date-scoped tables; no same-day result is admitted.
    past_by_day = collections.defaultdict(lambda: {"racelist": [], "horselist": []})
    for key, race in race_rows.items():
        past_by_day[key[1]]["racelist"].append(race)
        past_by_day[key[1]]["horselist"].extend(horse_rows.get(key, []))
    report = {"version": "nar_prior_day_recent_form_v1", "start": start, "end": end,
              "requested_max_races": max_races, "eligible": 0, "skipped": 0,
              "recent_form_win": 0, "recent_form_top3": 0, "baseline_unavailable": True,
              "data_policy": "Prior-day results only; no final odds, future cumulative statistics, or same-day results."}
    paired = []
    # Race distances are read from the archive, but only historical ratings
    # strictly earlier than the target date are eligible as horse features.
    distances = {}
    for race_key, (_, fields) in race_rows.items():
        value = fields.get("距離", "")
        distances[race_key] = int(value) if value.isdecimal() else 0
    processed = set()
    for venue, day, race_no in keys:
        date = dt.datetime.strptime(day, "%Y%m%d").date()
        earliest = (date-dt.timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
        for previous in sorted(d for d in past_by_day if earliest <= d < day and d not in processed):
            history_runs(past_by_day[previous], history)
            processed.add(previous)
        features = features_on(history, date.isoformat())
        runners = []
        for raw, fields in horse_rows[(venue, day, race_no)]:
            no = as_int(cell(raw, fields, "馬番", idx=5))
            finish = as_int(cell(raw, fields, "着順", idx=31))
            ident = horse_key(fields)
            if no and ident and finish and finish > 0:
                runners.append((no, finish, features.get(ident)))
        target_distance = distances.get((venue, day, race_no), 0)
        distance_scores = {}
        for no, _, f in runners:
            if f is None or not target_distance:
                continue
            # Find the horse identity from this race without using its result.
            horse = next((horse_key(fields) for raw, fields in horse_rows[(venue, day, race_no)]
                          if as_int(cell(raw, fields, "馬番", idx=5)) == no), None)
            runs = history.get(horse, {})
            eligible_runs = sorted(
                ((race_key, rating) for race_key, rating in runs.items()
                 if race_key[1] < day and rating is not None
                 and abs(distances.get(race_key, 0) - target_distance) <= 200),
                key=lambda item: (item[0][1], int(item[0][2])), reverse=True)[:3]
            if eligible_runs:
                weights = (3, 2, 1)
                distance_scores[no] = (.5 + sum(w*rating for w, (_, rating)
                    in zip(weights, eligible_runs))) / (1 + sum(weights[:len(eligible_runs)]))
        ranked = sorted(((f[0], no) for no, _, f in runners if f is not None),
                        key=lambda x: (-x[0], x[1]))
        winners = [no for no, rank, _ in runners if rank == 1]
        podium = {no for no, rank, _ in runners if rank <= 3}
        if len(runners) < 3 or len(ranked) < 3 or len(winners) != 1:
            report["skipped"] += 1
            continue
        top = ranked[0][1]
        # A predeclared alternative penalizes sparse historical observations.
        adjusted = sorted(
            ((f[0] - 0.025 * (3 - min(3, f[1])), no)
             for no, _, f in runners if f is not None),
            key=lambda x: (-x[0], x[1]))
        distance_adjusted = sorted(
            ((.7*f[0] + .3*distance_scores.get(no, f[0]), no)
             for no, _, f in runners if f is not None),
            key=lambda x: (-x[0], x[1]))
        paired.append({"day": day, "winner": winners[0],
                       "podium": podium, "base": top,
                       "coverage_adjusted": adjusted[0][1],
                       "distance_adjusted": distance_adjusted[0][1]})
        report["eligible"] += 1
        report["recent_form_win"] += top == winners[0]
        report["recent_form_top3"] += top in podium
    n = report["eligible"]
    report["recent_form_win_rate"] = round(100*report["recent_form_win"]/n, 2) if n else None
    report["recent_form_top3_rate"] = round(100*report["recent_form_top3"]/n, 2) if n else None
    # Split by date to avoid evaluating a candidate on its tuning sample.
    days = sorted({r["day"] for r in paired})
    boundary = days[max(0, int(len(days)*0.7)-1)] if days else None
    def metrics(rows, choice):
        count = len(rows)
        wins = sum(r[choice] == r["winner"] for r in rows)
        podium = sum(r[choice] in r["podium"] for r in rows)
        return {"races": count, "wins": wins, "top3": podium,
                "win_rate": round(100*wins/count, 2) if count else None,
                "top3_rate": round(100*podium/count, 2) if count else None}
    train = [r for r in paired if r["day"] <= boundary] if boundary else []
    test = [r for r in paired if r["day"] > boundary] if boundary else []
    variants = ("base", "coverage_adjusted", "distance_adjusted")
    selected = max(variants, key=lambda name: (
        metrics(train, name)["wins"], metrics(train, name)["top3"],
        name == "base")) if train else "base"
    report["holdout"] = {
        "split": "chronological_by_day_70_30",
        "distance_rule": "Within 200m, prior-day races only; 70% base + 30% distance form; no matching form falls back to base.",
        "last_training_day": boundary,
        "selected_on_training_only": selected,
        "training": {name: metrics(train, name) for name in variants},
        "test": {name: metrics(test, name) for name in variants},
        "selection_note": "Diagnostic only; production predictions unchanged."
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", required=True, help="YYYY-MM-DD")
    parser.add_argument("--end", required=True, help="YYYY-MM-DD")
    parser.add_argument("--max-races", type=int, default=1000)
    parser.add_argument("--output", default="nar-monthly-replay.json")
    args = parser.parse_args()
    start = dt.date.fromisoformat(args.start)
    end = dt.date.fromisoformat(args.end)
    if not (start <= end and 1 <= args.max_races <= 2000 and (end-start).days <= 120):
        parser.error("Require start <= end, <=120 days and 1..2000 races")
    first = (start-dt.timedelta(days=LOOKBACK_DAYS)).replace(day=1)
    last = end.replace(day=1)
    months = []
    month = first
    while month <= last:
        url = BASE_URL.split("?",1)[0]+"?"+urlencode(
            {"type":"monthly","k_year":month.year,"k_month":f"{month.month:02d}"})
        try:
            months.append(load_zip_tables(fetch_daily_zip(url)))
        except Exception as exc:
            raise SystemExit(f"Historical archive unavailable for {month:%Y-%m}: {exc}") from exc
        month = (month.replace(day=28)+dt.timedelta(days=4)).replace(day=1)
    result = replay(months, start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), args.max_races)
    Path(args.output).write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""Paired official-payout historical wide BOX comparison, read-only.

The 1-5 and confidence S:1-5 / A-C:2-6 candidates are built solely
from frozen ranking, confidence and market_at_lock, never from results.
"""
import argparse
import collections
import datetime as dt
import itertools
import json
from pathlib import Path
from backtest_nar_stake_allocation import eligible, official_market_index, official_settlement, metrics
from update_nar import load_zip_tables


def grade_from_frozen(r):
    rows = r.get("ranking") or []
    if len(rows) < 6:
        return None, "fewer_than_six_ranked"
    nos = [x.get("no") for x in rows]
    probs = [x.get("win_probability") for x in rows]
    if any(type(n) is not int or n < 1 for n in nos) or len(set(nos)) != len(nos):
        return None, "invalid_ranking"
    if any(type(p) not in (float, int) or not 0 <= p <= 1 for p in probs):
        return None, "invalid_probabilities"
    total = sum(probs)
    if abs(total - 1) > .005:
        return None, "invalid_probability_sum"
    ordered = sorted(probs, reverse=True)
    win, gap = 100 * ordered[0] / total, 100 * (ordered[0] - ordered[1]) / total
    grade = next((g for g, minimum, lead in (("S",55,20),("A",40,12),("B",28,5))
                  if win + 1e-9 >= minimum and gap + 1e-9 >= lead), "C")
    snap = r.get("market_at_lock") or {}
    quotes = {x.get("no"): x.get("odds") for x in snap.get("horses", []) if isinstance(x, dict)}
    complete = all(type(quotes.get(n)) in (int, float) and quotes[n] >= 1 for n in nos)
    timely = False
    try:
        observed = dt.datetime.fromisoformat(snap["updated_at"])
        locked = dt.datetime.fromisoformat(r["locked_at"])
        cutoff = dt.datetime.fromisoformat(r["cutoff_at"])
        timely = (all(t.tzinfo is not None for t in (observed,locked,cutoff))
                  and observed <= locked < cutoff and locked-observed <= dt.timedelta(minutes=15))
    except (KeyError, ValueError, TypeError):
        pass
    if (not complete or not timely) and grade in ("S", "A"):
        grade = "B"
    return grade, None


def paired(records, tables):
    official = official_market_index(tables)
    skipped = collections.Counter()
    grades = collections.Counter()
    rows = []
    ids = set()
    for record in records:
        if not isinstance(record, dict):
            skipped["invalid_record"] += 1
            continue
        payout, error = official_settlement(record, official)
        if error:
            skipped[error] += 1
            continue
        r = {**record, **payout}
        info, error = eligible(r)
        if error:
            skipped[error] += 1
            continue
        grade, error = grade_from_frozen(r)
        if error:
            skipped[error] += 1
            continue
        if r.get("id") in ids:
            skipped["duplicate_race"] += 1
            continue
        ids.add(r["id"])
        grades[grade] += 1
        ranked = [x["no"] for x in r["ranking"]]
        winners = info["wide"]
        def wager(nos):
            selected = set(itertools.combinations(sorted(nos), 2))
            returned = sum(winners.get(t, 0) for t in selected)
            return 1000, returned, {"wide": {"stake_yen":1000,"payout_yen":returned}}
        baseline = wager(ranked[:5])
        confidence = wager(ranked[:5] if grade == "S" else ranked[1:6])
        rows.append((r, grade, baseline, confidence))
    rows.sort(key=lambda x: (x[0]["date"],x[0]["start_at"],x[0]["id"]))
    days = sorted({r["date"] for r,_,_,_ in rows})
    n_early = max(1, int(len(days)*.7)) if len(days)>1 else len(days)
    early = set(days[:n_early])
    def group(part):
        return {"races":len(part), "baseline":metrics([x[2] for x in part]),
                "confidence":metrics([x[3] for x in part]),
                "paired_return_difference_yen":sum(x[3][1]-x[2][1] for x in part)}
    return {"status":"official_payouts_reconciled_frozen_confidence_not_authenticated",
            "eligible_races":len(rows),"excluded":dict(sorted(skipped.items())),
            "grades":dict(sorted(grades.items())),
            "stake_per_race_per_strategy_yen":1000,
            "all":group(rows),
            "earlier_dates":group([x for x in rows if x[0]["date"] in early]),
            "later_dates":group([x for x in rows if x[0]["date"] not in early]),
            "flat":group([x for x in rows if "帯広" not in x[0].get("venue","") and "ばんえい" not in x[0].get("venue","")]),
            "banei":group([x for x in rows if "帯広" in x[0].get("venue","") or "ばんえい" in x[0].get("venue","")]),
            "notes":["Hypothetical 1000 yen per strategy per race, same eligible races.",
                     "Only archived rankings and market_at_lock for confidence; official payouts for settlement.",
                     "Archived lock timestamps have not been independently authenticated.",
                     "Do not automatically switch production wagering based on historical returns."]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=Path("data/auto/nar_predictions.json"))
    p.add_argument("--official-zip",type=Path,required=True)
    p.add_argument("--month",default="2026-11")
    p.add_argument("--output",type=Path,default=Path("nar-confidence-wide-audit.json"))
    a=p.parse_args()
    data=json.loads(a.input.read_text(encoding="utf-8"))
    tables=load_zip_tables(a.official_zip.read_bytes())
    if "payback" not in tables:
        p.error("Official payback.csv missing")
    result=paired([r for r in data["races"] if str(r.get("date","")).startswith(a.month)],tables)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k not in ("notes",)},ensure_ascii=False))


if __name__=="__main__":
    main()

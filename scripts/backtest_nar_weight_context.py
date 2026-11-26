#!/usr/bin/env python3
"""Offline chronological paired experiment; never changes production forecasts."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timedelta
import json
import math
from pathlib import Path

CONDITIONS = ("良", "稍重", "重", "不良")
SLOPES = (-0.2, -0.1, 0., 0.1, 0.2)
MIN_TRAIN = 30
MIN_CONDITION = 20

def timestamp(value):
    try:
        v = datetime.fromisoformat(value)
        return v if v.tzinfo is not None else None
    except (TypeError, ValueError):
        return None

def finite(x):
    return type(x) in (int, float) and math.isfinite(x)

def prepare(r):
    if r.get("status") == "draft" or r.get("result_alternatives"):
        return None, "not_final_unique_result"
    locked, predicted, cutoff, start, settled = (timestamp(r.get(k)) for k in
        ("locked_at", "predicted_at", "cutoff_at", "start_at", "settled_at"))
    if not all((locked, predicted, cutoff, start, settled)) or not predicted <= locked < cutoff == start-timedelta(minutes=15) < start <= settled:
        return None, "invalid_times"
    if start.date().isoformat() != r.get("date"):
        return None, "invalid_date"
    ctx = r.get("entry_context_at_lock")
    if not isinstance(ctx, dict) or ctx.get("discipline") != "flat" or ctx.get("weight_kind") != "carried":
        return None, "no_flat_prelock_context"
    observed = timestamp(ctx.get("observed_at"))
    if observed is None or observed > predicted or observed.date() != start.date():
        return None, "invalid_context_time"
    condition = ctx.get("track_condition")
    if condition not in CONDITIONS:
        return None, "unknown_track"
    rows, weights = r.get("ranking"), ctx.get("horses")
    if not isinstance(rows, list) or len(rows) < 3 or not isinstance(weights, list) or len(rows) != len(weights):
        return None, "incomplete_field"
    if any(not isinstance(h, dict) for h in rows + weights):
        return None, "invalid_field"
    ids = [h.get("no") for h in rows]
    wids = [h.get("no") for h in weights]
    if any(type(n) is not int or not 1 <= n <= 30 for n in ids+wids) or len(set(ids)) != len(ids) or len(set(wids)) != len(wids) or set(ids) != set(wids):
        return None, "invalid_horse_ids"
    ww = {h["no"]: h.get("weight_kg") for h in weights}
    if any(not finite(w) or not 35 <= w <= 80 for w in ww.values()):
        return None, "incomplete_weight"
    probs = [h.get("win_probability") for h in rows]
    if any(not finite(p) or not 0 < p <= 1 for p in probs) or abs(sum(probs)-1) > .005:
        return None, "invalid_probability"
    podium = r.get("result")
    if not isinstance(podium, list) or len(podium) != 3 or any(type(n) is not int for n in podium) or len(set(podium)) != 3:
        return None, "invalid_result"
    if podium[0] not in ids:
        return None, "winner_outside_frozen_field"
    avg = sum(ww.values()) / len(ww)
    return {"id": r["id"], "day": r["date"], "venue": r.get("venue","unknown"),
            "predicted": predicted, "settled": settled, "condition": condition,
            "ids": ids, "p": [p/sum(probs) for p in probs],
            "relative": [ww[n]-avg for n in ids], "winner": ids.index(podium[0]),
            "podium": set(podium)}, None

def adjusted(row, beta):
    z = [math.log(p)+beta*w for p,w in zip(row["p"],row["relative"])]
    m = max(z)
    exp = [math.exp(x-m) for x in z]
    total = sum(exp)
    return [x/total for x in exp]

def fit(rows, center=0., minimum=MIN_TRAIN):
    if len(rows) < minimum:
        return center
    # Predeclared grid; modest regularization toward global slope.
    return min(SLOPES, key=lambda b: (
        sum(-math.log(adjusted(r,b)[r["winner"]]) for r in rows)/len(rows)
        + (b-center)**2, abs(b-center), b))

def stats(rows):
    out = {"races": len(rows)}
    for name in ("baseline","weight","weight_track"):
        win = top3 = 0
        ll = brier = 0.
        for r in rows:
            p = r[name]
            i = min(range(len(p)), key=lambda i:(-p[i],r["ids"][i]))
            win += i == r["winner"]
            top3 += r["ids"][i] in r["podium"]
            ll -= math.log(p[r["winner"]])
            brier += sum((v-(j==r["winner"]))**2 for j,v in enumerate(p))
        n = len(rows)
        out[name] = {"wins":win,"top3":top3,"win_rate":round(100*win/n,4) if n else None,
                     "top3_rate":round(100*top3/n,4) if n else None,
                     "log_loss":round(ll/n,6) if n else None,"brier":round(brier/n,6) if n else None}
    return out

def backtest(records):
    exclusions = Counter()
    groups = defaultdict(list)
    for r in records:
        if not isinstance(r,dict) or not isinstance(r.get("id"),str) or not r["id"]:
            exclusions["invalid_id"] += 1
        else:
            groups[r["id"]].append(r)
    eligible = []
    for g in groups.values():
        if len(g) != 1:
            exclusions["duplicate_id"] += len(g)
            continue
        row, reason = prepare(g[0])
        if row is None:
            exclusions[reason] += 1
        else:
            eligible.append(row)
    eligible.sort(key=lambda r:(r["day"],r["predicted"],r["id"]))
    byday = defaultdict(list)
    for r in eligible:
        byday[r["day"]].append(r)
    tested, history, fits = [], [], []
    for day, rows in sorted(byday.items()):
        # Entire day is held out; only earlier-day results known before its first forecast.
        earliest = min(r["predicted"] for r in rows)
        training = [r for r in history if r["settled"] < earliest]
        if len(training) < MIN_TRAIN:
            exclusions["warmup_or_unsettled_training"] += len(rows)
        else:
            global_beta = fit(training)
            bycondition = {c: [r for r in training if r["condition"] == c] for c in CONDITIONS}
            betas = {c:fit(v,global_beta,MIN_CONDITION) for c,v in bycondition.items()}
            fits.append({"date":day,"training_races":len(training),"weight_beta":global_beta,
                         "condition_betas":betas,"condition_training_counts":{c:len(v) for c,v in bycondition.items()}})
            for r in rows:
                tested.append({**r,"baseline":r["p"],"weight":adjusted(r,global_beta),
                               "weight_track":adjusted(r,betas[r["condition"]])})
        history.extend(rows)
    return {"version":"weight_context_walkforward_v1","status":"insufficient_test_data" if len(tested)<300 else "exploratory_only",
            "total_records":len(records),"eligible":len(eligible),"tested":len(tested),
            "excluded":dict(exclusions),"all":stats(tested),
            "by_condition":{c:stats([r for r in tested if r["condition"]==c]) for c in CONDITIONS},
            "by_venue":{v:stats([r for r in tested if r["venue"]==v]) for v in sorted({r["venue"] for r in tested})},
            "daily_fits":fits,"production_changed":False,
            "limitations":["No archive backfill; complete frozen pre-race weight and track required.",
                "Baseline is the stored forecast probability, not a refitted model.",
                "Track interaction is an exploratory proxy, not horse-specific going aptitude.",
                "Minimum 300 test races is a screening threshold, not proof of improvement.",
                "No ROI claims or wager instructions."]}

def selftest():
    from datetime import timezone
    def race(i, day, weight=54):
        start = datetime(2026,11,day,12,tzinfo=timezone(timedelta(hours=9)))
        predicted = start-timedelta(minutes=20)
        return {"id":str(i),"date":start.date().isoformat(),"venue":"浦和",
                "start_at":start.isoformat(),"cutoff_at":(start-timedelta(minutes=15)).isoformat(),
                "locked_at":predicted.isoformat(),"predicted_at":predicted.isoformat(),
                "settled_at":(start+timedelta(minutes=30)).isoformat(),"result":[2,1,3],
                "ranking":[{"no":1,"win_probability":.5},{"no":2,"win_probability":.3},{"no":3,"win_probability":.2}],
                "entry_context_at_lock":{"discipline":"flat","weight_kind":"carried","observed_at":predicted.isoformat(),
                    "track_condition":"良","horses":[{"no":1,"weight_kg":58},{"no":2,"weight_kg":weight},{"no":3,"weight_kg":56}]}}
    r=race(0,1)
    row,reason=prepare(r)
    assert reason is None and abs(sum(adjusted(row,-.2))-1)<1e-12
    assert adjusted(row,-.2)[1]>row["p"][1]
    assert prepare(race(1,1,None))[1]=="incomplete_weight"
    assert backtest([r,r])["excluded"]["duplicate_id"]==2
    records=[race(i,1) for i in range(30)]+[race(31,2),race(32,2)]
    out=backtest(records)
    assert out["tested"]==2 and out["daily_fits"][0]["training_races"]==30
    assert out["daily_fits"][0]["weight_beta"]<0
    assert out["all"]["baseline"]["wins"]==0
    assert out["status"]=="insufficient_test_data"
    records[-1]["result"]=[1,2,3]
    assert backtest(records)["daily_fits"]==out["daily_fits"]
    records[0]["settled_at"]=records[-1]["settled_at"]
    assert backtest(records)["tested"]==0
    print("10 chronological weight-context checks passed")

if __name__ == "__main__":
    p=argparse.ArgumentParser()
    p.add_argument("--input",default="data/auto/nar_predictions.json")
    p.add_argument("--output",default="nar-weight-context-backtest.json")
    p.add_argument("--selftest",action="store_true")
    a=p.parse_args()
    if a.selftest:
        selftest()
    else:
        data=json.loads(Path(a.input).read_text(encoding="utf-8"))
        report=backtest(data["races"])
        Path(a.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items() if k!="daily_fits"},ensure_ascii=False))

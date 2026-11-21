#!/usr/bin/env python3
"""Ten-strategy NAR diagnostics; never use outcome information to select tickets."""
import argparse
import collections
import datetime as dt
import itertools
import json
from pathlib import Path
from audit_nar_confidence_wide import grade_from_frozen
from backtest_nar_stake_allocation import eligible, official_market_index, official_settlement, metrics
from update_nar import load_zip_tables

def flat(r):
    return not ("帯広" in r.get("venue","") or "ばんえい" in r.get("venue",""))

def frozen_odds(r):
    snap=r.get("market_at_lock") or {}
    try:
        obs=dt.datetime.fromisoformat(snap["updated_at"])
        lock=dt.datetime.fromisoformat(r["locked_at"])
        cutoff=dt.datetime.fromisoformat(r["cutoff_at"])
        if any(x.tzinfo is None for x in (obs,lock,cutoff)) or not (obs<=lock<cutoff and lock-obs<=dt.timedelta(minutes=15)):
            return None
        quotes={x["no"]:x["odds"] for x in snap["horses"] if isinstance(x,dict) and type(x.get("no")) is int and type(x.get("odds")) in (int,float) and x["odds"]>=1}
        return quotes
    except (KeyError,TypeError,ValueError,AttributeError):
        return None

def bet(info,kind,tickets,units=1):
    if not tickets:
        return (0,0,{kind:{"stake_yen":0,"payout_yen":0}})
    stake=100*units*len(tickets)
    paid=0
    for t in tickets:
        if kind=="wide":
            prize=info["wide"].get(tuple(sorted(t)),0)
        else:
            prize=info["payout"][kind] if tuple(t)==info["winning"][kind] else 0
        paid+=units*prize
    return stake,paid,{kind:{"stake_yen":stake,"payout_yen":paid}}

def tickets(r,info,grade,method):
    ranked=[x["no"] for x in r["ranking"]]
    odds=frozen_odds(r)
    if method=="win_top1":
        return bet(info,"win",[(ranked[0],)])
    if method=="win_top1_s_a":
        return bet(info,"win",[(ranked[0],)] if grade in ("S","A") else [])
    if method=="win_value_110":
        if not odds:
            return bet(info,"win",[])
        prob=r["ranking"][0]["win_probability"]
        o=odds.get(ranked[0])
        return bet(info,"win",[(ranked[0],)] if o and prob*o>=1.10 else [])
    if method=="win_value_130":
        if not odds:
            return bet(info,"win",[])
        prob=r["ranking"][0]["win_probability"]
        o=odds.get(ranked[0])
        return bet(info,"win",[(ranked[0],)] if o and prob*o>=1.30 else [])
    if method=="wide_top3":
        return bet(info,"wide",list(itertools.combinations(ranked[:3],2)))
    if method=="wide_axis_top1_four":
        return bet(info,"wide",[(ranked[0],n) for n in ranked[1:5]])
    if method=="wide_axis_top2_three":
        return bet(info,"wide",[(ranked[1],n) for n in ranked[2:5]])
    if method=="wide_2points":
        return bet(info,"wide",[(ranked[0],ranked[1]),(ranked[0],ranked[2])])
    if method=="wide_1point":
        return bet(info,"wide",[(ranked[0],ranked[1])])
    if method=="wide_top3_s_a":
        return bet(info,"wide",list(itertools.combinations(ranked[:3],2)) if grade in ("S","A") else [])
    if method=="wide_top3_flat":
        return bet(info,"wide",list(itertools.combinations(ranked[:3],2)) if flat(r) else [])
    if method=="wide_top3_small_field":
        return bet(info,"wide",list(itertools.combinations(ranked[:3],2)) if len(r["ranking"])<=9 else [])
    if method=="wide_top3_large_field":
        return bet(info,"wide",list(itertools.combinations(ranked[:3],2)) if len(r["ranking"])>=10 else [])
    if method=="wide_rank2to4":
        return bet(info,"wide",list(itertools.combinations(ranked[1:4],2)))
    if method=="trio_frozen_first":
        return bet(info,"trio",[tuple(sorted(r["trio_tickets"][0]))])
    if method=="trifecta_frozen_first":
        return bet(info,"trifecta",[tuple(r["tickets"][0])])
    raise ValueError(method)

METHODS=("win_top1","win_top1_s_a","win_value_110","win_value_130",
         "wide_top3","wide_axis_top1_four","wide_axis_top2_three","wide_2points","wide_1point",
         "wide_top3_s_a","wide_top3_flat","wide_top3_small_field","wide_top3_large_field",
         "wide_rank2to4","trio_frozen_first","trifecta_frozen_first")

def compare(records,tables):
    market=official_market_index(tables)
    cohort=[]
    excluded=collections.Counter()
    seen=set()
    for r in records:
        if not isinstance(r,dict):
            excluded["invalid_record"]+=1
            continue
        official,reason=official_settlement(r,market)
        if reason:
            excluded[reason]+=1
            continue
        info,reason=eligible({**r,**official})
        if reason:
            excluded[reason]+=1
            continue
        grade,reason=grade_from_frozen(r)
        if reason:
            excluded[reason]+=1
            continue
        if r["id"] in seen:
            excluded["duplicate"]+=1
            continue
        seen.add(r["id"])
        cohort.append((r,info,grade))
    cohort.sort(key=lambda x:(x[0]["date"],x[0]["start_at"],x[0]["id"]))
    dates=sorted({r["date"] for r,_,_ in cohort})
    earlier=set(dates[:max(1,int(.7*len(dates)))]) if dates else set()
    result={}
    for method in METHODS:
        allrows=[(r,grade,tickets(r,info,grade,method)) for r,info,grade in cohort]
        result[method]={"all":metrics([x for _,_,x in allrows]),
                        "later_dates":metrics([x for r,_,x in allrows if r["date"] not in earlier]),
                        "purchased_races":sum(x[0]>0 for _,_,x in allrows)}
    venues={}
    odds_bands={}
    field_sizes={}
    grades={}
    for r,info,grade in cohort:
        win=tickets(r,info,grade,"win_top1")
        wide=tickets(r,info,grade,"wide_top3")
        for dest,key in ((venues,r["venue"]),(field_sizes,"small_<=9" if len(r["ranking"])<=9 else "large_>=10"),(grades,grade)):
            dest.setdefault(key,[]).append((win,wide))
        odds=frozen_odds(r)
        top=r["ranking"][0]["no"]
        if odds and top in odds:
            o=odds[top]
            band="1-2.9" if o<3 else ("3-5.9" if o<6 else ("6-9.9" if o<10 else "10+"))
            odds_bands.setdefault(band,[]).append((win,wide))
    def groups(d):
        return {k:{"races":len(v),"win":metrics([x[0] for x in v]),"wide_top3":metrics([x[1] for x in v])} for k,v in sorted(d.items())}
    return {"status":"official_payout_historical_comparison_prelock_not_authenticated",
            "eligible_races":len(cohort),"excluded":dict(sorted(excluded.items())),
            "methods":result,"by_venue":groups(venues),"by_top_win_odds":groups(odds_bands),
            "by_field_size":groups(field_sizes),"by_confidence":groups(grades),
            "availability":{"win_ev_filter":"testable_with_archived_fresh_win_odds_but_probability_uncalibrated",
                            "wide_ev_filter":"not_testable_no_archived_wide_odds_and_joint_probabilities",
                            "place_bets":"not_tested_no_official_place_payout_join",
                            "quinella":"not_tested_no_official_quinella_payout_join",
                            "track_running_style":"not_testable_as_prelock_features_from_monthly_results",
                            "calibration":"requires separate temporal probability audit",
                            "adaptive_stakes":"historical selective-stake comparisons are in nar-selective-wide.json"},
            "notes":["100 yen per ticket; different methods have different total stakes and are not equal-budget comparisons.",
                     "All filters are based on frozen pre-race fields, not results.",
                     "No out-of-sample optimization; later-date split is a diagnostic, not independent replication.",
                     "Historical timestamps are not independently authenticated; no production betting changes."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=Path("data/auto/nar_predictions.json"))
    p.add_argument("--official-zip",type=Path,required=True)
    p.add_argument("--month",default="2026-11")
    p.add_argument("--output",type=Path,default=Path("nar-strategy-matrix.json"))
    a=p.parse_args()
    raw=json.loads(a.input.read_text(encoding="utf-8"))
    tables=load_zip_tables(a.official_zip.read_bytes())
    if "payback" not in tables:
        p.error("Official payback missing")
    report=compare([r for r in raw["races"] if str(r.get("date","")).startswith(a.month)],tables)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"eligible_races":report["eligible_races"],"methods":{k:{"races":v["purchased_races"],"roi":v["all"]["roi_percent"],"net":v["all"]["net_yen"],"later_roi":v["later_dates"]["roi_percent"]} for k,v in report["methods"].items()},"availability":report["availability"]},ensure_ascii=False))
if __name__=="__main__":
    main()

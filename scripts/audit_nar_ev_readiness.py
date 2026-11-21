#!/usr/bin/env python3
"""Auditable odds readiness and predeclared calibration bins; no outcome-based betting."""
import argparse
import collections
import json
import math
from pathlib import Path
from audit_nar_ev_staking_shadow import valid_quote
from backtest_nar_stake_allocation import eligible, official_market_index, official_settlement
from update_nar import load_zip_tables

BINS=((0,.2),(.2,.3),(.3,.4),(.4,.5),(.5,.6),(.6,1.01))

def analyze(records,tables):
    market=official_market_index(tables)
    counts=collections.Counter()
    rows=[]
    seen=set()
    for r in records:
        if not isinstance(r,dict):
            counts["invalid_record"]+=1
            continue
        counts["total_records"]+=1
        ranking=r.get("ranking")
        if not isinstance(ranking,list) or not ranking or not isinstance(ranking[0],dict):
            counts["ranking_missing"]+=1
            continue
        top=ranking[0]
        no,p=top.get("no"),top.get("win_probability")
        if type(no) is not int or type(p) not in (int,float) or not math.isfinite(p) or not 0<p<1:
            counts["probability_invalid"]+=1
            continue
        counts["valid_top_probability"]+=1
        quotes,reason=valid_quote(r)
        if reason:
            counts["odds_"+reason]+=1
        elif no not in quotes:
            counts["top_odds_missing"]+=1
        else:
            counts["fresh_top_odds"]+=1
            if p*quotes[no]>=1.10:
                counts["shadow_ev110_candidates"]+=1
        payout,reason=official_settlement(r,market)
        if reason:
            counts["settlement_"+reason]+=1
            continue
        _,reason=eligible({**r,**payout})
        if reason:
            counts["eligibility_"+reason]+=1
            continue
        key=r.get("id")
        if not isinstance(key,str) or not key or key in seen:
            counts["duplicate_or_missing_id"]+=1
            continue
        seen.add(key)
        rows.append((r["date"],p,int(no==r["result"][0])))
    rows.sort(key=lambda x:x[0])
    dates=sorted({x[0] for x in rows})
    train_dates=set(dates[:max(1,int(.7*len(dates)))]) if dates else set()
    def summarize(data):
        n=len(data)
        if not n:
            return {"races":0,"predicted_win_percent":None,"actual_win_percent":None,"brier":None,"bins":[]}
        bins=[]
        for lo,hi in BINS:
            subset=[(p,y) for _,p,y in data if lo<=p<hi]
            if subset:
                bins.append({"range":f"{lo:.2f}-{min(hi,1):.2f}","races":len(subset),
                             "mean_predicted_percent":round(100*sum(p for p,y in subset)/len(subset),2),
                             "actual_win_percent":round(100*sum(y for p,y in subset)/len(subset),2)})
        return {"races":n,"predicted_win_percent":round(100*sum(p for _,p,y in data)/n,2),
                "actual_win_percent":round(100*sum(y for _,p,y in data)/n,2),
                "brier":round(sum((p-y)**2 for _,p,y in data)/n,5),"bins":bins}
    return {"status":"diagnostic_only_no_live_staking",
            "counts":dict(sorted(counts.items())),
            "all":summarize(rows),
            "earlier_dates":summarize([x for x in rows if x[0] in train_dates]),
            "later_dates":summarize([x for x in rows if x[0] not in train_dates]),
            "holdout_days":len(dates)-len(train_dates),
            "notes":["Official payouts validate result only, not pre-lock timestamp authenticity.",
                     "Odds readiness counts all archived predictions; calibration uses independently reconciled outcomes.",
                     "Calibration bins were fixed before analysis. No calibration model is fitted on holdout.",
                     "No staking approval or claim of positive expectation."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=Path("data/auto/nar_predictions.json"))
    p.add_argument("--official-zip",type=Path,required=True)
    p.add_argument("--month",default="2026-11")
    p.add_argument("--output",type=Path,default=Path("nar-ev-readiness.json"))
    a=p.parse_args()
    records=json.loads(a.input.read_text(encoding="utf-8"))["races"]
    tables=load_zip_tables(a.official_zip.read_bytes())
    if "payback" not in tables:
        p.error("Official payback missing")
    result=analyze([r for r in records if str(r.get("date","")).startswith(a.month)],tables)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="notes"},ensure_ascii=False))
if __name__=="__main__":
    main()

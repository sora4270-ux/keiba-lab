#!/usr/bin/env python3
"""Read-only, same-cohort NAR wide-ticket selection and budget comparison."""
import argparse
import collections
import itertools
import json
from pathlib import Path
from audit_nar_confidence_wide import grade_from_frozen
from backtest_nar_stake_allocation import eligible, official_market_index, official_settlement, metrics
from update_nar import load_zip_tables

BUDGET=1000
# All choices are defined before seeing results. No fitted odds or payout leakage.
PLANS=("old_top5_box","confidence_box","top3_all","selective_s_top3","selective_s_a","selective_s_a_flat","grade_budget")

def wager(info, ranked, grade, plan, venue):
    flat=not ("帯広" in venue or "ばんえい" in venue)
    if plan=="old_top5_box":
        nos, stake=ranked[:5],1000
    elif plan=="confidence_box":
        nos, stake=(ranked[:5] if grade=="S" else ranked[1:6]),1000
    elif plan=="top3_all":
        nos,stake=ranked[:3],900
    elif plan=="selective_s_top3":
        nos,stake=(ranked[:3],900) if grade=="S" else ([],0)
    elif plan=="selective_s_a":
        nos,stake=(ranked[:3],900) if grade=="S" else ((ranked[1:4],600) if grade=="A" else ([],0))
    elif plan=="selective_s_a_flat":
        nos,stake=(ranked[:3],900) if grade=="S" and flat else ((ranked[1:4],600) if grade=="A" and flat else ([],0))
    else:
        nos,stake=(ranked[:3],600) if grade=="S" else ((ranked[1:4],300) if grade=="A" else ((ranked[1:3],100) if grade=="B" else ([],0)))
    pairs=list(itertools.combinations(sorted(nos),2))
    # If budget does not cover all pairs, do not pretend a 10-point BOX was purchased.
    if stake < 100*len(pairs):
        pairs=[]
        stake=0
    if not pairs:
        return (0,0,{"wide":{"stake_yen":0,"payout_yen":0}})
    each,rem=divmod(stake//100,len(pairs))
    payout=sum((each+(i<rem))*info["wide"].get(pair,0) for i,pair in enumerate(pairs))
    return (stake,payout,{"wide":{"stake_yen":stake,"payout_yen":payout}})

def compare(records,tables):
    market=official_market_index(tables)
    excluded=collections.Counter()
    cohort=[]
    ids=set()
    for record in records:
        if not isinstance(record,dict):
            excluded["invalid_record"]+=1
            continue
        settlement,reason=official_settlement(record,market)
        if reason:
            excluded[reason]+=1
            continue
        info,reason=eligible({**record,**settlement})
        if reason:
            excluded[reason]+=1
            continue
        grade,reason=grade_from_frozen(record)
        if reason:
            excluded[reason]+=1
            continue
        if record["id"] in ids:
            excluded["duplicate_race"]+=1
            continue
        ids.add(record["id"])
        cohort.append((record,info,grade))
    cohort.sort(key=lambda x:(x[0]["date"],x[0]["start_at"],x[0]["id"]))
    days=sorted({r["date"] for r,_,_ in cohort})
    early=set(days[:max(1,int(.7*len(days)))]) if days else set()
    results={}
    for plan in PLANS:
        rows=[(r,grade,wager(info,[x["no"] for x in r["ranking"]],grade,plan,r.get("venue",""))) for r,info,grade in cohort]
        active=[x for _,_,x in rows if x[0]]
        results[plan]={
            "all":metrics([x for _,_,x in rows]),
            "later_dates":metrics([x for r,_,x in rows if r["date"] not in early]),
            "flat":metrics([x for r,_,x in rows if "帯広" not in r.get("venue","") and "ばんえい" not in r.get("venue","")]),
            "banei":metrics([x for r,_,x in rows if "帯広" in r.get("venue","") or "ばんえい" in r.get("venue","")]),
            "purchased_races":len(active),"skipped_races":len(rows)-len(active)}
    return {"status":"historical_hypothetical_official_payout_join_prelock_unverified",
            "eligible_races":len(cohort),"excluded":dict(sorted(excluded.items())),
            "stake_policy":"100 yen units, max 1000 yen/race; unspent budget stays unspent",
            "plans":results,"notes":["Not real bets; historic prelock timestamps not independently authenticated.",
                                     "Same eligible cohort, but selective strategies wager less total money.",
                                     "ROI alone is not evidence of future edge; no production changes.",
                                     "No pre-race wide quote archive: cannot test true wide EV threshold."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=Path("data/auto/nar_predictions.json"))
    p.add_argument("--official-zip",type=Path,required=True)
    p.add_argument("--month",default="2026-11")
    p.add_argument("--output",type=Path,default=Path("nar-selective-wide.json"))
    a=p.parse_args()
    records=json.loads(a.input.read_text(encoding="utf-8"))["races"]
    tables=load_zip_tables(a.official_zip.read_bytes())
    if "payback" not in tables:
        p.error("Official payback missing")
    report=compare([r for r in records if str(r.get("date","")).startswith(a.month)],tables)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"eligible_races":report["eligible_races"],
                      "plans":{k:{"purchased_races":v["purchased_races"],"stake_yen":v["all"]["stake_yen"],"payout_yen":v["all"]["payout_yen"],"roi_percent":v["all"]["roi_percent"],"net_yen":v["all"]["net_yen"],"later_roi":v["later_dates"]["roi_percent"]} for k,v in report["plans"].items()}},ensure_ascii=False))

if __name__=="__main__":
    main()

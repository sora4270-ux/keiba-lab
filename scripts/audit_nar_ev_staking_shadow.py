#!/usr/bin/env python3
"""Pre-race-only shadow stake plans. Never places bets or claims profitability."""
import argparse
import datetime as dt
import json
import math
from pathlib import Path

def valid_quote(r):
    try:
        snap=r["market_at_lock"]
        updated=dt.datetime.fromisoformat(snap["updated_at"])
        locked=dt.datetime.fromisoformat(r["locked_at"])
        cutoff=dt.datetime.fromisoformat(r["cutoff_at"])
        start=dt.datetime.fromisoformat(r["start_at"])
        if any(x.tzinfo is None for x in (updated,locked,cutoff,start)):
            return None,"timezone_missing"
        if not (updated<=locked<cutoff==start-dt.timedelta(minutes=15)):
            return None,"invalid_cutoff"
        if locked-updated>dt.timedelta(minutes=15):
            return None,"stale_odds"
        horses=snap["horses"]
        if not isinstance(horses,list):
            return None,"invalid_market"
        quotes={}
        for h in horses:
            if (not isinstance(h,dict) or type(h.get("no")) is not int or h["no"] < 1
                    or type(h.get("odds")) not in (int,float)
                    or not math.isfinite(h["odds"]) or h["odds"] < 1):
                return None,"invalid_market"
            if h["no"] in quotes:
                return None,"duplicate_market_horse"
            quotes[h["no"]]=h["odds"]
        ranking=r.get("ranking") or []
        if not quotes or any(h.get("no") not in quotes for h in ranking):
            return None,"incomplete_market"
        return quotes,None
    except (KeyError,TypeError,ValueError,AttributeError):
        return None,"market_missing_or_malformed"

def evaluate(r,bankroll=30000,edge=1.10,kelly_fraction=.25,max_fraction=.01,calibrated=False):
    """Return shadow recommendations only; gate live staking on external calibration."""
    result={"race_id":r.get("id"),"status":"skip","reason":None,"candidate_no":None,
            "odds":None,"win_probability":None,"expected_return_ratio":None,
            "shadow_fixed_yen":0,"shadow_fractional_kelly_yen":0,
            "live_wager_allowed":False}
    ranking=r.get("ranking") or []
    if not isinstance(ranking,list) or not ranking or not isinstance(ranking[0],dict):
        result["reason"]="ranking_missing"
        return result
    first=ranking[0]
    no=first.get("no")
    prob=first.get("win_probability")
    if type(no) is not int or type(prob) not in (float,int) or not math.isfinite(prob) or not 0<prob<1:
        result["reason"]="invalid_probability"
        return result
    quotes,reason=valid_quote(r)
    if reason:
        result["reason"]=reason
        return result
    odds=quotes.get(no)
    if odds is None:
        result["reason"]="top_horse_odds_missing"
        return result
    ev=prob*odds
    result.update(candidate_no=no,odds=odds,win_probability=prob,expected_return_ratio=round(ev,6))
    if ev<edge:
        result["reason"]="below_edge_threshold"
        return result
    # Probability calibration must be independently verified before a wager can be actionable.
    result["status"]="shadow_candidate"
    result["reason"]="probability_calibration_not_verified" if not calibrated else "simulation_only"
    result["shadow_fixed_yen"]=100
    kelly=max(0,(ev-1)/(odds-1))
    cap=bankroll*max_fraction
    result["shadow_fractional_kelly_yen"]=100*math.floor(min(cap,bankroll*kelly*kelly_fraction)/100)
    return result

def report(records,bankroll=30000,edge=1.10,kelly_fraction=.25,max_fraction=.01):
    rows=[evaluate(r,bankroll,edge,kelly_fraction,max_fraction) for r in records if isinstance(r,dict)]
    from collections import Counter
    reasons=Counter(x["reason"] for x in rows)
    return {"status":"shadow_only_uncalibrated_no_real_wagers",
            "races":len(rows),"shadow_candidates":sum(x["status"]=="shadow_candidate" for x in rows),
            "fixed_shadow_total_yen":sum(x["shadow_fixed_yen"] for x in rows),
            "kelly_shadow_total_yen":sum(x["shadow_fractional_kelly_yen"] for x in rows),
            "reasons":dict(sorted(reasons.items())),
            "assumptions":{"bankroll_yen":bankroll,"minimum_expected_return_ratio":edge,
                           "fractional_kelly":kelly_fraction,"max_race_bankroll_fraction":max_fraction},
            "rows":rows,
            "notes":["All decisions use only archived pre-race ranking and odds, never outcomes.",
                     "Forecast calibration is not established. The shadow amount is NOT a purchase recommendation.",
                     "No profit or positive expectation is established from uncalibrated probabilities.",
                     "Bankroll is a static scenario, not an evolving account balance."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=Path("data/auto/nar_predictions.json"))
    p.add_argument("--month",default="2026-11")
    p.add_argument("--output",type=Path,default=Path("nar-ev-staking-shadow.json"))
    p.add_argument("--bankroll",type=int,default=30000)
    a=p.parse_args()
    if a.bankroll<100:
        p.error("bankroll must be at least 100")
    data=json.loads(a.input.read_text(encoding="utf-8"))
    result=report([r for r in data["races"] if str(r.get("date","")).startswith(a.month)],a.bankroll)
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in result.items() if k!="rows"},ensure_ascii=False))
if __name__=="__main__":
    main()

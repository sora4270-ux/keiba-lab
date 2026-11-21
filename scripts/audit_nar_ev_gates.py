#!/usr/bin/env python3
"""Conservative evidence gates for EV staking; diagnostics only, never authorizes wagering."""
import argparse
import json
import math
from pathlib import Path

def assess(readiness,shadow,min_coverage=.95,min_holdout=300,min_days=14):
    counts=readiness.get("counts",{})
    total=counts.get("total_records",0)
    fresh=counts.get("fresh_top_odds",0)
    coverage=fresh/total if total else 0
    all_stats=readiness.get("all",{})
    later=readiness.get("later_dates",{})
    days=readiness.get("holdout_days",0)
    gaps=[]
    if not total:
        gaps.append("no_records")
    if coverage<min_coverage:
        gaps.append("odds_coverage_below_target")
    if later.get("races",0)<min_holdout or days<min_days:
        gaps.append("insufficient_temporal_holdout")
    # Brier is only an error metric, not a certification of calibration.
    if not all_stats.get("bins") or not later.get("bins"):
        gaps.append("calibration_bins_missing")
    else:
        # Maximum observed bin gap on holdout; small bins remain noisy.
        if any(b["races"]<30 for b in later["bins"]):
            gaps.append("sparse_holdout_probability_bins")
        if any(abs(b["actual_win_percent"]-b["mean_predicted_percent"])>5 for b in later["bins"]):
            gaps.append("holdout_probability_miscalibration")
    if shadow.get("shadow_candidates",0)==0:
        gaps.append("no_positive_ev_candidates")
    # Archived data alone cannot prove authentic pre-lock capture.
    gaps.append("independent_prelock_capture_not_authenticated")
    gaps.append("unverified_forward_profitability")
    return {"status":"blocked_no_live_staking",
            "gates_passed":False,
            "total_records":total,
            "fresh_top_odds":fresh,
            "odds_coverage_percent":round(100*coverage,2),
            "target_odds_coverage_percent":round(100*min_coverage,2),
            "holdout_races":later.get("races",0),
            "holdout_days":days,
            "shadow_candidates":shadow.get("shadow_candidates",0),
            "blocking_reasons":gaps,
            "priority_actions":[
                "Log source timestamp, capture timestamp, lock timestamp and immutable quote hash at T-15; distinguish archived vs independently attested.",
                "Reduce missing odds with retries before T-15 and explicit stale/missing reason codes; never backfill after start.",
                "Collect at least 300 independently held-out races over 14 dates before fitting or promoting a calibration model.",
                "Evaluate calibration error and hypothetical ROI on later untouched races with confidence intervals.",
                "Retain real wagering disabled until separate manual approval and independent forward validation."],
            "notes":["Thresholds are operational safeguards, not evidence that passing implies positive expected value.",
                     "Do not tune thresholds on the same holdout to manufacture a profitable strategy."]}

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--readiness",type=Path,default=Path("nar-ev-readiness.json"))
    p.add_argument("--shadow",type=Path,default=Path("nar-ev-staking-shadow.json"))
    p.add_argument("--output",type=Path,default=Path("nar-ev-readiness-gates.json"))
    a=p.parse_args()
    result=assess(json.loads(a.readiness.read_text(encoding="utf-8")),
                  json.loads(a.shadow.read_text(encoding="utf-8")))
    a.output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False))
if __name__=="__main__":
    main()

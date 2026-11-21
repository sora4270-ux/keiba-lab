#!/usr/bin/env python3
"""Read-only multi-month official NAR confidence reliability audit.

No fitting to holdout, no changing production grade thresholds, no betting.
Missing official months or frozen predictions are explicitly reported.
"""
import argparse
import collections
import json
import math
from pathlib import Path
from urllib.parse import urlencode

from audit_nar_confidence_wide import grade_from_frozen, paired
from backtest_nar_stake_allocation import eligible, official_market_index, official_settlement
from update_nar import BASE_URL, fetch_daily_zip, load_zip_tables


def reliability(records, tables):
    market = official_market_index(tables)
    bins = collections.defaultdict(list)
    excluded = collections.Counter()
    for r in records:
        if not isinstance(r, dict):
            excluded["invalid_record"] += 1
            continue
        payout, reason = official_settlement(r, market)
        if reason:
            excluded[reason] += 1
            continue
        _, reason = eligible({**r, **payout})
        if reason:
            excluded[reason] += 1
            continue
        grade, reason = grade_from_frozen(r)
        if reason:
            excluded[reason] += 1
            continue
        p = r["ranking"][0]["win_probability"]
        # The same first-ranked horse that the UI marks as the win favorite.
        if type(p) not in (float,int) or not math.isfinite(p):
            excluded["invalid_top_probability"] += 1
            continue
        outcome = int(r["ranking"][0]["no"] == r["result"][0])
        bins[grade].append((p,outcome))
    def summarize(values):
        n=len(values)
        return {"races":n,
                "mean_predicted_win_percent":round(100*sum(p for p,_ in values)/n,2) if n else None,
                "actual_win_percent":round(100*sum(y for _,y in values)/n,2) if n else None,
                "brier_score":round(sum((p-y)**2 for p,y in values)/n,5) if n else None}
    return {"all":summarize([v for values in bins.values() for v in values]),
            "by_grade":{grade:summarize(bins.get(grade,[])) for grade in ("S","A","B","C")},
            "excluded":dict(sorted(excluded.items()))}


def audit_months(records, archives, requested):
    report={"status":"diagnostic_only_no_recalibration","months":{},
            "requested_months":requested,"missing_months":[],
            "notes":["No official ZIP or frozen forecasts means no historical validation for that month.",
                     "Confidence grade thresholds remain unchanged; Brier score is a diagnostic, not proof of calibration.",
                     "Archived prelock timestamps are not independently authenticated.",
                     "No production strategy or live stake changes."]}
    for month in requested:
        month_records=[r for r in records if isinstance(r,dict) and str(r.get("date","")).startswith(month)]
        tables=archives.get(month)
        if tables is None or "payback" not in tables:
            report["missing_months"].append(month)
            report["months"][month]={"status":"official_archive_unavailable","frozen_predictions":len(month_records)}
            continue
        if not month_records:
            report["missing_months"].append(month)
            report["months"][month]={"status":"no_frozen_predictions","frozen_predictions":0}
            continue
        pair=paired(month_records,tables)
        report["months"][month]={"status":"audited","frozen_predictions":len(month_records),
                                 "paired_wide":pair,"confidence_reliability":reliability(month_records,tables)}
    report["verified_month_count"]=sum(x["status"]=="audited" for x in report["months"].values())
    report["multi_month_validated"]=report["verified_month_count"]>=2
    return report


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",type=Path,default=Path("data/auto/nar_predictions.json"))
    p.add_argument("--months",nargs="+",default=["2026-10","2026-11"])
    p.add_argument("--official-dir",type=Path,default=None)
    p.add_argument("--output",type=Path,default=Path("nar-confidence-multimonth.json"))
    a=p.parse_args()
    records=json.loads(a.input.read_text(encoding="utf-8"))["races"]
    archives={}
    for month in a.months:
        year,mo=month.split("-")
        try:
            if a.official_dir:
                raw=(a.official_dir/(month+".zip")).read_bytes()
            else:
                url=BASE_URL.split("?",1)[0]+"?"+urlencode({"type":"monthly","k_year":int(year),"k_month":str(int(mo))})
                raw=fetch_daily_zip(url)
            archives[month]=load_zip_tables(raw)
        except (OSError,ValueError,RuntimeError,KeyError) as exc:
            print("Official archive unavailable",month,type(exc).__name__)
    report=audit_months(records,archives,a.months)
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"status":report["status"],"verified_month_count":report["verified_month_count"],
                      "missing_months":report["missing_months"],
                      "months":{m:{"status":x["status"],
                                   "races":x.get("paired_wide",{}).get("eligible_races",0),
                                   "reliability":x.get("confidence_reliability",{}).get("all")}
                                for m,x in report["months"].items()}},ensure_ascii=False))


if __name__=="__main__":
    main()

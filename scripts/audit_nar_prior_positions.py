#!/usr/bin/env python3
"""Read-only retrospective coverage of previous-run early corner positions.

No forecast weights, tickets, betting decisions or frozen records are changed.
The archive is retrospective; it is not proof of pre-race availability.
"""
import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
import json
from pathlib import Path
import re
import unicodedata
from recent_form import corner_positions, horse_key
from update_nar import row_key, load_zip_tables, as_int, BASE_URL, fetch_daily_zip
from urllib.parse import urlencode

UNKNOWN = "insufficient_history"


def early_corner(fields):
    # Use the first named 1st/2nd corner, not 4th corner as a pace proxy.
    options = {}
    for i in range(1,9):
        label = unicodedata.normalize("NFKC", fields.get(f"コーナー名称{i}","")).strip()
        if re.fullmatch(r"(?:第)?[12](?:角|コーナー)", label):
            pos = corner_positions(fields.get(f"コーナー通過順{i}",""))
            if pos:
                options.setdefault(int(re.search(r"[12]",label).group()),[]).append(pos)
    for k in sorted(options):
        if len(options[k]) == 1:
            return options[k][0]
    return {}


def index_archive(tables):
    races = defaultdict(list)
    entries = defaultdict(list)
    for item in tables.get("racelist",[]):
        k = row_key(item,())
        if k and "帯広" not in k[0] and "ばんえい" not in k[0]:
            races[k].append(item[1])
    for item in tables.get("horselist",[]):
        k = row_key(item,())
        if k in races:
            entries[k].append(item[1])
    history = defaultdict(list)
    targets = []
    quality = Counter()
    labels = Counter()
    for k, rows in sorted(entries.items(),key=lambda x:(x[0][1],x[0][0],x[0][2])):
        if len(races[k]) != 1:
            quality["duplicate_race_metadata"] += 1
            continue
        ids = [horse_key(r) for r in rows]
        nos = [as_int(r.get("馬番")) for r in rows]
        id_count, no_count = Counter(ids), Counter(nos)
        for i in range(1,9):
            label = unicodedata.normalize("NFKC", races[k][0].get(f"コーナー名称{i}","")).strip()
            if label:
                labels[label] += 1
        corners = early_corner(races[k][0])
        quality["races_with_early_corner"] += int(bool(corners))
        for r, ident, no in zip(rows,ids,nos):
            if not ident or id_count[ident]!=1 or no is None or not 1<=no<=30 or no_count[no]!=1:
                quality["invalid_or_duplicate_identity"] += 1
                continue
            targets.append((k,ident))
            rank = as_int(r.get("着順"))
            if rank is not None and 1<=rank<=30:
                history[ident].append((k,corners.get(no)))
    return history,targets,quality,labels


def prior_summary(runs, target_day, window):
    target = date.fromisoformat(target_day)
    earliest = (target-timedelta(days=90)).strftime("%Y%m%d")
    cutoff = target.strftime("%Y%m%d")
    prior = [(k,p) for k,p in runs if earliest<=k[1]<cutoff]
    # A horse with ambiguous same-day records is not assigned a style.
    counts = Counter(k[1] for k,_ in prior)
    prior.sort(key=lambda x:x[0][1],reverse=True)
    latest = prior[:window]
    valid = [p for k,p in latest if p is not None and counts[k[1]]==1]
    # Descriptive positional bands, not official running-style labels.
    label = UNKNOWN
    avg = None
    if len(latest)==window and len(valid)==window:
        avg = sum(valid)/window
        label = ("front" if avg>=.8 else "forward" if avg>=.55
                 else "midfield" if avg>=.25 else "rear")
    return {"prior_runs":len(latest),"usable_runs":len(valid),
            "mean_early_position":round(avg,4) if avg is not None else None,
            "position_band":label}


def audit(tables, target_month=None):
    history, targets, quality, labels = index_archive(tables)
    result = {str(w):Counter() for w in (3,5)}
    for key, ident in targets:
        d = date.fromisoformat(key[1][:4]+"-"+key[1][4:6]+"-"+key[1][6:])
        if target_month and d.strftime("%Y-%m") != target_month:
            continue
        for w in (3,5):
            x = prior_summary(history[ident],d.isoformat(),w)
            c = result[str(w)]
            c["runner_entries"] += 1
            c["full_window"] += int(x["prior_runs"]==w)
            c["all_positions_available"] += int(x["usable_runs"]==w)
            c[x["position_band"]] += 1
    return {"status":"retrospective_archive_coverage_only","quality":dict(quality),
            "target_month":target_month,
            "corner_label_counts":dict(labels),
            "windows":{k:dict(v) for k,v in result.items()},
            "notes":["Only completed races on strictly earlier dates within 90 days are used.",
                     "First or second corner only; fourth corner is not substituted.",
                     "Position bands are descriptive heuristics, not official running styles.",
                     "Missing archive months or missing positions limit coverage; unknown is not a zero position.",
                     "No live ranking, forecast, ticket or real-money decision is changed."]}


def required_months(target_month):
    first = date.fromisoformat(target_month+"-01")
    lower = first - timedelta(days=90)
    current = first
    months = []
    while current >= lower.replace(day=1):
        months.append(current.strftime("%Y-%m"))
        current = (current-timedelta(days=1)).replace(day=1)
    return months


def merge_months(archives):
    # Restrict each source to its own month so overlapping files cannot double count.
    out = {"racelist":[], "horselist":[]}
    coverage = {}
    for month, tables in archives.items():
        counts = {}
        for kind in out:
            selected = []
            for item in tables.get(kind,[]):
                k = row_key(item,())
                if k and k[1][:6] == month.replace("-",""):
                    selected.append(item)
            counts[kind] = len(selected)
            out[kind].extend(selected)
        coverage[month] = counts
    return out, coverage


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--zip",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("nar-prior-position-audit.json"))
    p.add_argument("--target-month",help="YYYY-MM corresponding to supplied ZIP")
    p.add_argument("--fetch-prior-months",action="store_true")
    a=p.parse_args()
    if a.fetch_prior_months and not a.target_month:
        p.error("--target-month is required with --fetch-prior-months")
    if a.target_month:
        months = required_months(a.target_month)
        archives = {a.target_month:load_zip_tables(a.zip.read_bytes())}
        errors = {}
        if a.fetch_prior_months:
            for month in months[1:]:
                year, number = month.split("-")
                url = BASE_URL.split("?")[0]+"?"+urlencode(
                    {"type":"monthly","k_year":int(year),"k_month":number})
                try:
                    archives[month] = load_zip_tables(fetch_daily_zip(url))
                except Exception as exc:
                    errors[month] = type(exc).__name__
        merged, coverage = merge_months(archives)
        report = audit(merged,a.target_month)
        report["archive_coverage"] = coverage
        report["required_months"] = months
        report["missing_months"] = [m for m in months if not all(coverage.get(m,{}).get(k,0)>0 for k in ("racelist","horselist"))]
        report["archive_errors"] = errors
        report["required_month_files_present"] = not report["missing_months"]
    else:
        report=audit(load_zip_tables(a.zip.read_bytes()))
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__":
    main()

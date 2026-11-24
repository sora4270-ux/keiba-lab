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
from update_nar import row_key, load_zip_tables, as_int

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
    for k, rows in sorted(entries.items(),key=lambda x:(x[0][1],x[0][0],x[0][2])):
        if len(races[k]) != 1:
            quality["duplicate_race_metadata"] += 1
            continue
        ids = [horse_key(r) for r in rows]
        nos = [as_int(r.get("馬番")) for r in rows]
        id_count, no_count = Counter(ids), Counter(nos)
        corners = early_corner(races[k][0])
        for r, ident, no in zip(rows,ids,nos):
            if not ident or id_count[ident]!=1 or no is None or not 1<=no<=30 or no_count[no]!=1:
                quality["invalid_or_duplicate_identity"] += 1
                continue
            targets.append((k,ident))
            rank = as_int(r.get("着順"))
            if rank is not None and 1<=rank<=30:
                history[ident].append((k,corners.get(no)))
    return history,targets,quality


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


def audit(tables):
    history, targets, quality = index_archive(tables)
    result = {str(w):Counter() for w in (3,5)}
    for key, ident in targets:
        d = date.fromisoformat(key[1][:4]+"-"+key[1][4:6]+"-"+key[1][6:])
        for w in (3,5):
            x = prior_summary(history[ident],d.isoformat(),w)
            c = result[str(w)]
            c["runner_entries"] += 1
            c["full_window"] += int(x["prior_runs"]==w)
            c["all_positions_available"] += int(x["usable_runs"]==w)
            c[x["position_band"]] += 1
    return {"status":"retrospective_archive_coverage_only","quality":dict(quality),
            "windows":{k:dict(v) for k,v in result.items()},
            "notes":["Only completed races on strictly earlier dates within 90 days are used.",
                     "First or second corner only; fourth corner is not substituted.",
                     "Position bands are descriptive heuristics, not official running styles.",
                     "A single monthly archive truncates prior history; missing data remains unknown.",
                     "No live ranking, forecast, ticket or real-money decision is changed."]}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--zip",type=Path,required=True)
    p.add_argument("--output",type=Path,default=Path("nar-prior-position-audit.json"))
    a=p.parse_args()
    report=audit(load_zip_tables(a.zip.read_bytes()))
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,ensure_ascii=False))

if __name__=="__main__":
    main()

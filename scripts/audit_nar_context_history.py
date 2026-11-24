"""Descriptive, prior-date-only history coverage by race context.

Final race condition is retrospective metadata, not an authenticated T-15 observation.
No forecast, ticket, stake or ranking is changed.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
import unicodedata
from update_nar import row_key, cell, as_int
from recent_form import horse_key


def clean(value):
    return unicodedata.normalize("NFKC", str(value or "")).strip()


def valid_distance(n):
    return n if type(n) is int and 600 <= n <= 4000 else None


def context_audit(tables, target_month):
    metadata = defaultdict(list)
    rows_by_race = defaultdict(list)
    for item in tables.get("racelist", []):
        k = row_key(item, ())
        if not k or "帯広" in k[0] or "ばんえい" in k[0]:
            continue
        raw, fields = item
        distance = valid_distance(as_int(cell(raw, fields, "距離", idx=23)))
        ground = clean(cell(raw, fields, "馬場", "馬場状態", idx=25))
        metadata[k].append((distance, ground if ground in ("良","稍重","重","不良") else None))
    for item in tables.get("horselist", []):
        k = row_key(item, ())
        if k in metadata:
            rows_by_race[k].append(item)
    by_horse = defaultdict(list)
    by_jockey_venue = defaultdict(list)
    targets = []
    quality = Counter()
    for k, rows in rows_by_race.items():
        if len(metadata[k]) != 1:
            quality["duplicate_race_metadata"] += 1
            continue
        distance, ground = metadata[k][0]
        ids = [horse_key(f) for _,f in rows]
        nos = [as_int(cell(raw,f,"馬番",idx=5)) for raw,f in rows]
        ic, nc = Counter(ids), Counter(nos)
        try:
            day = date.fromisoformat(k[1][:4]+"-"+k[1][4:6]+"-"+k[1][6:])
        except ValueError:
            quality["invalid_date"] += 1
            continue
        for (raw,f),ident,no in zip(rows,ids,nos):
            if not ident or ic[ident]!=1 or no is None or not 1<=no<=30 or nc[no]!=1:
                quality["invalid_or_duplicate_identity"] += 1
                continue
            jockey = clean(cell(raw,f,"騎手コード","騎手ID"))
            # If no stable ID exists, do not silently join different people by name.
            jockey = jockey or None
            rank = as_int(cell(raw,f,"着順",idx=31))
            rec = (day,k[0],distance,ground,jockey,rank)
            targets.append((ident,rec))
            if rank is not None and 1<=rank<=30:
                by_horse[ident].append(rec)
                if jockey:
                    by_jockey_venue[(jockey,k[0])].append(rec)
    counts = Counter()
    groups = defaultdict(Counter)
    for ident,r in targets:
        day,venue,distance,ground,jockey,rank = r
        if target_month and day.strftime("%Y-%m") != target_month:
            continue
        earliest = day-timedelta(days=90)
        prior = [x for x in by_horse[ident] if earliest<=x[0]<day]
        dates = Counter(x[0] for x in prior)
        prior = [x for x in prior if dates[x[0]]==1]
        matches = {
            "exact_distance": [x for x in prior if distance is not None and x[2]==distance],
            "same_ground": [x for x in prior if ground is not None and x[3]==ground],
            "same_venue": [x for x in prior if x[1]==venue],
            "same_jockey": [x for x in prior if jockey is not None and x[4]==jockey],
            "jockey_venue": [x for x in by_jockey_venue.get((jockey,venue),[]) if earliest<=x[0]<day],
        }
        counts["target_entries"] += 1
        counts["target_distance_known"] += int(distance is not None)
        counts["target_ground_known"] += int(ground is not None)
        counts["target_jockey_id_known"] += int(jockey is not None)
        for label,items in matches.items():
            counts[label+"_with_history"] += int(bool(items))
            counts[label+"_with_3plus"] += int(len(items)>=3)
        if rank is not None and 1<=rank<=30:
            for label,value in (("distance",str(distance) if distance else "unknown"),
                                ("ground",ground or "unknown"),
                                ("venue",venue)):
                g=groups[(label,value)]
                g["finished_runner_entries"]+=1
                g["first_place_entries"]+=int(rank==1)
                g["top3_entries"]+=int(rank<=3)
    return {"status":"descriptive_archive_context_audit","coverage":dict(counts),
            "quality":dict(quality),
            "result_context":[{"dimension":k,"value":v,**dict(c)} for (k,v),c in sorted(groups.items())],
            "notes":["Prior matches use completed runs on earlier dates in a 90-day window.",
                     "Same-ground coverage uses final target condition, not a proven pre-race value.",
                     "Jockey matching requires an explicit stable ID; names alone are not joined.",
                     "Result groups are descriptive counts of runner entries, not forecasts or returns."]}

"""Retrospective archive experiment; not an authenticated pre-lock forecast.
All features from strictly earlier dates. Final target going is scenario metadata.
"""
from collections import Counter, defaultdict
from datetime import date, timedelta
import math
from recent_form import horse_key
from update_nar import row_key, cell, as_int

GROUND = ("良","稍重","重","不良")
MODELS = ("prior_form","distance","ground","early_position","combined")

def index(tables, early_corner):
    metadata, entries = defaultdict(list), defaultdict(list)
    for item in tables.get("racelist", []):
        k = row_key(item, ())
        if k and not any(s in k[0] for s in ("帯広","ばんえい")):
            raw, f = item
            d = as_int(cell(raw,f,"距離",idx=23))
            g = cell(raw,f,"馬場","馬場状態",idx=25)
            metadata[k].append((d,g,early_corner(f)))
    for item in tables.get("horselist", []):
        k = row_key(item,())
        if k in metadata:
            entries[k].append(item)
    races, history, excluded = [], defaultdict(list), Counter()
    for k, items in entries.items():
        if len(metadata[k]) != 1:
            excluded["ambiguous_metadata"] += 1
            continue
        d,g,early = metadata[k][0]
        try:
            day = date.fromisoformat(k[1][:4]+"-"+k[1][4:6]+"-"+k[1][6:])
        except ValueError:
            excluded["invalid_date"] += 1
            continue
        rows = []
        for raw,f in items:
            rank=as_int(cell(raw,f,"着順",idx=31))
            if rank is None or not 1 <= rank <= 30:
                continue
            rows.append({"no":as_int(cell(raw,f,"馬番",idx=5)),"id":horse_key(f),"rank":rank})
        if len(rows)<3 or any(not r["id"] or not r["no"] or not 1<=r["no"]<=30 for r in rows) or len({r["id"] for r in rows})!=len(rows) or len({r["no"] for r in rows})!=len(rows):
            excluded["invalid_finished_field"] += 1
            continue
        if sorted(r["rank"] for r in rows if r["rank"]<=3)!=[1,2,3]:
            excluded["ambiguous_podium"] += 1
            continue
        for r in rows:
            # Current race early position is stored solely for use on later days.
            history[r["id"]].append((day,d,g,r["rank"]<=3,early.get(r["no"])))
        if d is None or not 600<=d<=4000 or g not in GROUND:
            excluded["unknown_target_context"] += 1
            continue
        races.append((day,k[0],d,g,rows))
    return races,history,excluded

def features(runs,day,d,g):
    earlier=[r for r in runs if day-timedelta(days=90)<=r[0]<day]
    counts=Counter(r[0] for r in earlier)
    prior=sorted((r for r in earlier if counts[r[0]]==1),reverse=True,key=lambda r:r[0])
    # Neutral prior prevents unobserved aptitude from becoming a penalty.
    base=(sum(r[3] for r in prior)+1.5)/(len(prior)+5)
    def context(rows):
        return (sum(r[3] for r in rows)+5*base)/(len(rows)+5)-base
    distance=[r for r in prior if r[1]==d]
    ground=[r for r in prior if r[2]==g]
    early=[r[4] for r in prior[:3] if type(r[4]) in (int,float) and math.isfinite(r[4]) and 0<=r[4]<=1]
    # Early positioning is an exploratory proxy, not an official style label.
    pace=(sum(early)/3-.5) if len(early)==3 else 0.
    return {"base":base,"distance":context(distance),"ground":context(ground),
            "early":pace,"distance_n":len(distance),"ground_n":len(ground),"early_n":len(early),"prior_n":len(prior)}

def audit(tables,target_month,early_corner):
    races,history,excluded=index(tables,early_corner)
    tally=Counter()
    results={m:Counter() for m in MODELS}
    groups=defaultdict(lambda:{m:Counter() for m in MODELS})
    for day,venue,d,g,rows in races:
        if target_month and day.strftime("%Y-%m")!=target_month:
            continue
        fs=[features(history[r["id"]],day,d,g) for r in rows]
        tally["target_races"]+=1
        tally["runner_rows"]+=len(fs)
        for label in ("prior","distance","ground"):
            tally[label+"_history"]+=sum(f[label+"_n"]>0 for f in fs)
            tally[label+"_3plus"]+=sum(f[label+"_n"]>=3 for f in fs)
        tally["early_3plus"]+=sum(f["early_n"]==3 for f in fs)
        # Compare identical races; require actual prior form on every runner.
        if any(not f["prior_n"] for f in fs):
            excluded["missing_prior_form_in_field"]+=1
            continue
        if not any(f["distance_n"] or f["ground_n"] or f["early_n"]==3 for f in fs):
            excluded["no_context_features"]+=1
            continue
        tally["paired_races"]+=1
        scores={
            "prior_form":[f["base"] for f in fs],
            "distance":[f["base"]+f["distance"] for f in fs],
            "ground":[f["base"]+f["ground"] for f in fs],
            "early_position":[f["base"]+.1*f["early"] for f in fs],
            "combined":[f["base"]+.5*f["distance"]+.5*f["ground"]+.1*f["early"] for f in fs]}
        for m,s in scores.items():
            top=min(range(len(rows)),key=lambda i:(-s[i],rows[i]["no"]))
            for c in (results[m],groups[(venue,g)][m]):
                c["races"]+=1
                c["wins"]+=rows[top]["rank"]==1
                c["top3"]+=rows[top]["rank"]<=3
    def render(c):
        n=c["races"]
        return {"races":n,"wins":c["wins"],"top3":c["top3"],"win_rate":round(100*c["wins"]/n,2) if n else None,"top3_rate":round(100*c["top3"]/n,2) if n else None}
    return {"version":"horse_context_archive_v1","status":"retrospective_exploratory_only",
            "target_month":target_month,"coverage":dict(tally),"excluded":dict(excluded),
            "models":{m:render(c) for m,c in results.items()},
            "by_venue_ground":[{"venue":v,"ground":g,"models":{m:render(c) for m,c in cs.items()}} for (v,g),cs in sorted(groups.items())],
            "limitations":["Finished runners only; cancellations and incomplete fields can bias coverage.",
                "Final target going and archive identities are not authenticated T-15 observations.",
                "Coefficients are fixed exploratory heuristics, not trained or production probabilities.",
                "Only earlier dates in 90-day window; no current-race positions used.",
                "Not a comparison with production predictions; no ROI or deployment claim."]}

def selftest():
    day=date(2026,11,25)
    prior=[(day-timedelta(days=i),1400,"良",True,.9) for i in (1,2,3)]
    f=features(prior,day,1400,"良")
    assert f["prior_n"]==3 and f["distance_n"]==3 and f["ground_n"]==3 and f["early_n"]==3
    assert f["distance"]>0 and f["ground"]>0 and f["early"]>0
    assert features(prior+[(day,1400,"良",False,0.)],day,1400,"良")==f
    assert features(prior+[(day+timedelta(days=1),1400,"良",False,0.)],day,1400,"良")==f
    assert features([],day,1400,"良")["distance"]==0
    assert features(prior,day,1600,"重")["ground"]==0
    assert features(prior+[prior[0]],day,1400,"良")["prior_n"]==2
    print("7 horse-context checks passed")

if __name__=="__main__":
    selftest()

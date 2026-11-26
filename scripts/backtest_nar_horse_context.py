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

# Predeclared small grid. Choose by first-place accuracy, then simpler weights.
# These are exploratory coefficients, not production probabilities.
WEIGHT_GRID = tuple((d,g,e) for d in (0.,.5,1.) for g in (0.,.5,1.) for e in (0.,.05,.1))
MIN_FIT_RACES = 100
MIN_TEST_RACES = 100

def selection(features_rows, rows, weights):
    d,g,e=weights
    return min(range(len(rows)),key=lambda i:(-(features_rows[i]["base"]+d*features_rows[i]["distance"]+g*features_rows[i]["ground"]+e*features_rows[i]["early"]),rows[i]["no"]))

def paired_summary(records, weights):
    counts=Counter()
    for day, fs, rows in records:
        a=rows[selection(fs,rows,(0.,0.,0.))]["rank"]
        b=rows[selection(fs,rows,weights)]["rank"]
        counts["baseline_win"]+=a==1
        counts["candidate_win"]+=b==1
        counts["baseline_top3"]+=a<=3
        counts["candidate_top3"]+=b<=3
        counts["candidate_only_win"]+=b==1 and a!=1
        counts["baseline_only_win"]+=a==1 and b!=1
    n=len(records)
    x,y=counts["candidate_only_win"],counts["baseline_only_win"]
    discordant=x+y
    # Exact two-sided sign/McNemar test, descriptive only (races may be dependent).
    p=min(1.,2*sum(math.comb(discordant,k) for k in range(min(x,y)+1))/2**discordant) if discordant else 1.
    return {"races":n,**dict(counts),"win_delta_pp":round(100*(counts["candidate_win"]-counts["baseline_win"])/n,4) if n else None,
            "top3_delta_pp":round(100*(counts["candidate_top3"]-counts["baseline_top3"])/n,4) if n else None,
            "paired_p_value_descriptive":round(p,6) if n else None}

def choose_weights(records):
    return min(WEIGHT_GRID,key=lambda w:(-sum(rows[selection(fs,rows,w)]["rank"]==1 for _,fs,rows in records),sum(v!=0 for v in w),sum(w),w))

def chronological_split(records):
    days=sorted({r[0] for r in records})
    if len(days)<2:
        return {"status":"insufficient_days","fit_races":len(records),"test_races":0}
    # Whole calendar days only, fixed first 60% of dates for selection.
    boundary=days[max(1,int(.6*len(days)))]
    fit=[r for r in records if r[0]<boundary]
    test=[r for r in records if r[0]>=boundary]
    out={"status":"insufficient_samples","fit_races":len(fit),"test_races":len(test),"test_first_date":boundary.isoformat(),
         "grid_size":len(WEIGHT_GRID),"previously_inspected_period":True,"production_changed":False}
    if len(fit)<MIN_FIT_RACES or len(test)<MIN_TEST_RACES:
        return out
    w=choose_weights(fit)
    out.update(status="retrospective_split_only",weights=dict(zip(("distance","ground","early"),w)),
               fit=paired_summary(fit,w),test=paired_summary(test,w),
               fixed_combined_test=paired_summary(test,(.5,.5,.1)),
               daily_test=[{"date":day.isoformat(),**paired_summary([r for r in test if r[0]==day],w)} for day in sorted({r[0] for r in test})])
    return out

def audit(tables,target_month,early_corner):
    races,history,excluded=index(tables,early_corner)
    tally=Counter()
    paired=[]
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
        paired.append((day,fs,rows))
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
            "chronological_weight_selection":chronological_split(paired),
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
    fs=[{"base":.5,"distance":0.,"ground":0.,"early":0.},
        {"base":.49,"distance":.15,"ground":0.,"early":0.}]
    rows=[{"no":1,"rank":2},{"no":2,"rank":1}]
    sample=[(day-timedelta(days=1),fs,rows)]*100+[(day,fs,rows)]*100
    split=chronological_split(sample)
    assert split["fit_races"]==100 and split["test_races"]==100
    assert split["weights"]["distance"]>0 and split["weights"]["ground"]==0
    assert split["test"]["candidate_only_win"]==100
    assert split["test"]["baseline_only_win"]==0
    changed=[(day,fs,[{"no":1,"rank":1},{"no":2,"rank":2}])]*100
    assert chronological_split(sample[:100]+changed)["weights"]==split["weights"]
    assert chronological_split(sample[:100])["status"]=="insufficient_days"
    assert chronological_split(sample[:101])["status"]=="insufficient_samples"
    print("7 chronological coefficient checks passed")

if __name__=="__main__":
    selftest()

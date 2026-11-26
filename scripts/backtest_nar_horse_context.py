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
            no=as_int(cell(raw,f,"馬番",idx=5))
            rows.append({"no":no,"id":horse_key(f),"rank":rank,"actual_early_position":early.get(no)})
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

STYLE_BANDS = ("front","forward","midfield","rear","unknown")

def style_band(f):
    # Descriptive prior-position bands, not official tactical labels.
    if f.get("early_n")!=3:
        return "unknown"
    p=f.get("early")
    if type(p) not in (int,float) or not math.isfinite(p) or not -.5<=p<=.5:
        return "unknown"
    return "front" if p>=.3-1e-9 else "forward" if p>=.05-1e-9 else "midfield" if p>=-.25-1e-9 else "rear"

def field_pressure(fs):
    bands=Counter(style_band(f) for f in fs)
    known=len(fs)-bands["unknown"]
    # A pressure proxy, not a forecast of elapsed time or actual speed.
    if not fs or known*5<len(fs)*4:
        return "unknown",bands
    forward=bands["front"]+bands["forward"]
    # Missing styles could cross the boundary; abstain in that case.
    threshold=max(3,math.ceil(len(fs)*.4))
    low=forward<=1
    if low and forward+bands["unknown"]<=1:
        label="low"
    elif forward>=threshold:
        label="high"
    elif forward>=2 and forward+bands["unknown"]<threshold:
        label="medium"
    else:
        label="unknown"
    return label,bands

def position_audit(records):
    counts=Counter()
    style_counts=Counter()
    transition=defaultdict(Counter)
    groups=defaultdict(Counter)
    for day,fs,rows in records:
        label,bands=field_pressure(fs)
        counts["races"]+=1
        style_counts.update(bands)
        groups[label]["races"]+=1
        # Target-race observed positions are labels only, never features.
        observed={r["no"]:r.get("actual_early_position") for r in rows}
        valid=lambda p:type(p) in (int,float) and math.isfinite(p) and 0<=p<=1
        for f,r in zip(fs,rows):
            band=style_band(f)
            p=observed[r["no"]]
            if band!="unknown" and valid(p):
                transition[band][style_band({"early_n":3,"early":p-.5})]+=1
        if label=="unknown" or not all(valid(p) for p in observed.values()):
            continue
        counts["evaluable_fields"]+=1
        g=groups[label]
        g["evaluable_fields"]+=1
        leaders={n for n,p in observed.items() if p==max(observed.values())}
        known=[i for i,f in enumerate(fs) if style_band(f)!="unknown"]
        if not known:
            continue
        # Accuracy of expected leading position, not race winner accuracy.
        top=min(known,key=lambda i:(-fs[i]["early"],rows[i]["no"]))
        hit=rows[top]["no"] in leaders
        counts["expected_leader_hits"]+=hit
        g["expected_leader_hits"]+=hit
        counts["random_leader_expected_hits"]+=len(leaders)/len(rows)
        g["random_leader_expected_hits"]+=len(leaders)/len(rows)
    def render(c):
        n=c["evaluable_fields"]
        return {"races":c["races"],"evaluable_fields":n,"expected_leader_hits":c["expected_leader_hits"],
                "leader_hit_rate":round(100*c["expected_leader_hits"]/n,2) if n else None,
                "random_reference_rate":round(100*c["random_leader_expected_hits"]/n,2) if n else None}
    return {"status":"descriptive_position_proxy_only","all":render(counts),
            "style_counts":dict(style_counts),"position_transition":{k:dict(v) for k,v in transition.items()},
            "pressure_groups":{k:render(groups[k]) for k in ("low","medium","high","unknown")},
            "limitations":["At least three previous early positions per classified runner; at least 80% field coverage for pressure.",
                "Pressure is historical forward-position density, not measured pace; no section times.",
                "Target positions are validation labels only. Finished-field archive is not a verified pre-race field.",
                "No production forecast, ranking or wager changes."]}

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
            "field_position_experiment":position_audit(paired),
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
    def fpos(p):
        return {"early_n":3,"early":p-.5} if p is not None else {"early_n":0,"early":0.}
    assert [style_band(fpos(p)) for p in (.9,.6,.4,.1,None)]==list(STYLE_BANDS)
    assert field_pressure([fpos(p) for p in (.9,.8,.7,.2,.1)])[0]=="high"
    assert field_pressure([fpos(p) for p in (.9,.2,.2,.1,.1)])[0]=="low"
    assert field_pressure([fpos(p) for p in (.9,.8,.2,.1,.1)])[0]=="medium"
    assert field_pressure([fpos(p) for p in (.9,.8,.2,.1,None)])[0]=="unknown"
    assert field_pressure([fpos(p) for p in (.9,None,None,.1,.1)])[0]=="unknown"
    ff=[fpos(p) for p in (.9,.7,.1)]
    rr=[{"no":1,"rank":3,"actual_early_position":1.},{"no":2,"rank":1,"actual_early_position":.5},{"no":3,"rank":2,"actual_early_position":0.}]
    report=position_audit([(day,ff,rr)])
    assert report["all"]["expected_leader_hits"]==1
    rr[0]["actual_early_position"]=None
    assert position_audit([(day,ff,rr)])["all"]["evaluable_fields"]==0
    print("8 field position checks passed")

if __name__=="__main__":
    selftest()

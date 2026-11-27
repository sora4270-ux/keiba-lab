#!/usr/bin/env python3
"""Reproducible release decision; historical exploration never grants live approval."""
import argparse, collections, datetime as dt, hashlib, itertools, json, math, random
from pathlib import Path
from backtest_nar_stake_allocation import eligible, official_market_index, official_settlement, PLANS, settle_one
from audit_nar_confidence_wide import grade_from_frozen
from audit_nar_ev_staking_shadow import valid_quote
from audit_nar_strategy_matrix import tickets, METHODS, bet
from record_nar_frozen_ledger import digest
from update_nar import load_zip_tables, row_key, cell, as_int

SPLIT = '2026-11-20'  # Existing history has already been inspected: diagnostic, not pristine holdout.

def metrics(rows):
    rows = [x for x in rows if x['stake_yen'] > 0]
    stake=sum(x['stake_yen'] for x in rows); paid=sum(x['return_yen'] for x in rows)
    equity=peak=dd=losing=max_losing=hits=0
    for x in rows:
        net=x['return_yen']-x['stake_yen']; equity+=net; peak=max(peak,equity); dd=max(dd,peak-equity)
        hits+=x['return_yen']>0
        losing=losing+1 if net<0 else 0; max_losing=max(max_losing,losing)
    # Cluster resampling keeps correlated same-day races together.
    daily=collections.defaultdict(lambda:[0,0])
    for x in rows:
        daily[x['date']][0]+=x['stake_yen']; daily[x['date']][1]+=x['return_yen']
    blocks=list(daily.values()); ci=None
    if len(blocks)>=5:
        rng=random.Random(20261127); samples=[]
        for _ in range(2000):
            selected=rng.choices(blocks,k=len(blocks)); samples.append(100*sum(x[1] for x in selected)/sum(x[0] for x in selected))
        samples.sort(); ci=[round(samples[49],2),round(samples[1949],2)]
    return dict(races=len(rows),hit_races=hits,hit_rate_percent=round(100*hits/len(rows),2) if rows else None,
                stake_yen=stake,return_yen=paid,net_yen=paid-stake,roi_percent=round(100*paid/stake,2) if stake else None,
                max_consecutive_net_losses=max_losing,max_drawdown_yen=dd,daily_cluster_bootstrap_roi_95_percent=ci)

def calibration(rows, offset=0):
    pairs=[(min(.999999,max(.000001,r['probability']+offset)),r['won']) for r in rows]
    if not pairs: return {'races':0}
    bins=[]
    for low,high in ((0,.2),(.2,.3),(.3,.4),(.4,.5),(.5,.6),(.6,1.01)):
        subset=[(p,y) for p,y in pairs if low<=p<high]
        if subset: bins.append({'low':low,'high':min(1,high),'races':len(subset),'mean_probability':sum(p for p,y in subset)/len(subset),'actual_rate':sum(y for p,y in subset)/len(subset)})
    return {'races':len(pairs),'mean_probability':sum(p for p,y in pairs)/len(pairs),'actual_rate':sum(y for p,y in pairs)/len(pairs),
            'brier':sum((p-y)**2 for p,y in pairs)/len(pairs),'bins':bins}

def analyze(records,tables,ledger):
    market=official_market_index(tables); excluded=collections.Counter(); cohort=[]; ids=collections.Counter(r.get('id') for r in records if isinstance(r,dict))
    ledger_index={e['id']:e for e in ledger['entries']}; integrity=collections.Counter()
    runner_status=collections.defaultdict(dict)
    for raw,fields in tables.get('horselist',[]):
        key=row_key((raw,fields),())
        if key:
            no=as_int(cell(raw,fields,'馬番',idx=5)); rank=cell(raw,fields,'着順',idx=31)
            runner_status[key][no]=rank
    for r in records:
        if not isinstance(r,dict): excluded['malformed']+=1; continue
        if ids[r.get('id')]!=1: excluded['duplicate_id']+=1; continue
        e=ledger_index.get(r['id'])
        if not e or e['sha256']!=digest(r): integrity['missing_or_changed']+=1
        else: integrity[e['observation_status']]+=1
        payout,why=official_settlement(r,market)
        if why: excluded[why]+=1;continue
        info,why=eligible({**r,**payout})
        if why: excluded[why]+=1;continue
        # Do not fabricate zero returns or refunds for incomplete/abnormal runners.
        statuses=runner_status.get((r['venue'],r['date'].replace('-',''),r['race_no']),{})
        if any(not as_int(statuses.get(h['no'],'')) for h in r['ranking']):
            excluded['runner_status_or_refund_review']+=1;continue
        grade,why=grade_from_frozen(r)
        if why: excluded[why]+=1;continue
        quote,why=valid_quote(r)
        cohort.append((r,info,grade,why is None))
    cohort.sort(key=lambda x:(x[0]['start_at'],x[0]['id']))
    plans={}
    for method in METHODS+tuple(PLANS)+('trio_frozen_all','trifecta_frozen_all','wide_confidence_box'):

        rows=[]
        for r,info,grade,fresh in cohort:
            if method=='trio_frozen_all': value=bet(info,'trio',info['tickets']['trio'])
            elif method=='trifecta_frozen_all': value=bet(info,'trifecta',info['tickets']['trifecta'])
            elif method=='wide_confidence_box':
                ranked=[x['no'] for x in r['ranking']]; chosen=ranked[:5] if grade=='S' else ranked[1:6]
                value=bet(info,'wide',list(itertools.combinations(chosen,2)))
            else: value=settle_one(info,PLANS[method]) if method in PLANS else tickets(r,info,grade,method)
            spent,paid,_=value
            # Value policies require strict odds validation (including finite and duplicate checks).
            if method.startswith('win_value') and not fresh: spent=paid=0
            rows.append({'id':r['id'],'date':r['date'],'venue':r['venue'],'grade':grade,'stake_yen':spent,'return_yen':paid})
        plans[method]={'all':metrics(rows),'earlier':metrics([x for x in rows if x['date']<SPLIT]),'later_diagnostic':metrics([x for x in rows if x['date']>=SPLIT]),
            'by_venue':{k:metrics([x for x in rows if x['venue']==k]) for k in sorted({x['venue'] for x in rows})},
            'by_confidence':{k:metrics([x for x in rows if x['grade']==k]) for k in sorted({x['grade'] for x in rows})}}
    # Train-only method selection. Later data is evaluated once here, never used to choose the method.
    candidates=[m for m in METHODS if plans[m]['earlier']['races']>=100]
    selected=max(candidates,key=lambda m:plans[m]['earlier']['roi_percent']) if candidates else None
    probs=[]
    for r,info,grade,fresh in cohort:
        p=r['ranking'][0].get('win_probability')
        if type(p) in (int,float) and math.isfinite(p) and 0<p<1:
            probs.append({'date':r['date'],'probability':p,'won':int(r['ranking'][0]['no']==r['result'][0])})
    train=[x for x in probs if x['date']<SPLIT]; later=[x for x in probs if x['date']>=SPLIT]
    offset=sum(x['won']-x['probability'] for x in train)/len(train) if train else 0
    return {'schema_version':1,'status':'blocked','real_money_allowed':False,'saved_races':len(records),'verified_diagnostic_races':len(cohort),
        'excluded':dict(excluded),'ledger_integrity':dict(integrity),'split_date':SPLIT,'methods':plans,
        'train_selected_method':selected,'selection_min_train_races':100,'calibration':{'train':calibration(train),'later_raw':calibration(later),'train_only_offset':offset,'later_calibrated_shadow':calibration(later,offset)},
        'blockers':['historical_prelock_observations_not_independently_authenticated','no_pristine_forward_holdout_for_frozen_policy','no_validated_profitable_production_policy','risk_limits_only_enforced_inside_this_app'],
        'notes':['All amounts are hypothetical; no real purchases are inferred.','Official result-time payouts independently downloaded; abnormal/unknown runner statuses excluded, never counted as losses.','Later-date diagnostics are previously inspected history, not unused data. No production method adopted.','Net loss streak means return below stake; partial hits can be losses. Bootstrap is descriptive, not a guarantee or multiple-testing correction.','Calibration correction is fit only on earlier dates and remains shadow-only.']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--official-zip',type=Path,required=True);p.add_argument('--output',type=Path,default=Path('data/auto/nar_release.json'));a=p.parse_args()
    source=Path('data/auto/nar_predictions.json').read_bytes();official=a.official_zip.read_bytes()
    report=analyze(json.loads(source)['races'],load_zip_tables(official),json.loads(Path('data/auto/nar_frozen_ledger.json').read_text()))
    report.update(generated_at=dt.datetime.now(dt.timezone.utc).isoformat(),forecast_sha256=hashlib.sha256(source).hexdigest(),official_sha256=hashlib.sha256(official).hexdigest(),official_source='https://www.keiba.go.jp/KeibaWeb/DataDownload/RaceDataDownload?type=monthly&k_year=2026&k_month=11')
    a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='methods'},ensure_ascii=False))
if __name__=='__main__': main()

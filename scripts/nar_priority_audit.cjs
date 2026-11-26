#!/usr/bin/env node
'use strict';
// Diagnostic only. Never modifies predictions or betting decisions.
function audit(payload, snapshot="unknown"){
  if(!Array.isArray(payload.races)||!payload.races.length)throw Error("Missing race records");
  const counts=new Map();for(const r of payload.races)counts.set(r.id,(counts.get(r.id)||0)+1);
  const valid=r=>r.id&&counts.get(r.id)===1&&r.status!=="draft"&&Array.isArray(r.result)&&r.result.length===3&&r.result.every(Number.isInteger)&&new Set(r.result).size===3&&!r.result_alternatives&&Array.isArray(r.ranking)&&r.ranking.length>=3&&r.top3?.[0]?.no===r.ranking[0]?.no&&Date.parse(r.predicted_at)<=Date.parse(r.locked_at)&&Date.parse(r.locked_at)<Date.parse(r.cutoff_at)&&Date.parse(r.cutoff_at)===Date.parse(r.start_at)-900000;
  function grade(r){
    const rows=r.ranking,ps=rows.map(h=>h.win_probability),total=ps.reduce((a,b)=>a+b,0);
    if(rows.some(h=>!Number.isInteger(h.no)||h.no<1)||new Set(rows.map(h=>h.no)).size!==rows.length||ps.some(p=>!Number.isFinite(p)||p<0||p>1)||Math.abs(total-1)>.005)return "unrated";
    ps.sort((a,b)=>b-a);const win=100*ps[0]/total,gap=100*(ps[0]-ps[1])/total;
    const raw=[["S",55,20],["A",40,12],["B",28,5]].find(([,m,l])=>win+1e-9>=m&&gap+1e-9>=l)?.[0]||"C";
    const quotes=new Map((r.market_at_lock?.horses||[]).map(h=>[Number(h.no),Number(h.odds)])),o=Date.parse(r.market_at_lock?.updated_at),l=Date.parse(r.locked_at);
    const timely=rows.every(h=>Number.isFinite(quotes.get(h.no))&&quotes.get(h.no)>=1)&&o<=l&&l-o<=900000;
    return !timely&&["S","A"].includes(raw)?"B":raw;
  }
  const pct=(a,b)=>b?+(100*a/b).toFixed(2):null;
  function stats(rows){
    const wins=rows.filter(r=>r.top3[0].no===r.result[0]).length,top3=rows.filter(r=>r.result.includes(r.top3[0].no)).length;
    const priced=rows.filter(r=>Number.isSafeInteger(r.payouts?.win)&&r.payouts.win>0);
    const returned=priced.reduce((s,r)=>s+(r.top3[0].no===r.result[0]?r.payouts.win:0),0);
    return {races:rows.length,wins,top3,win_rate:pct(wins,rows.length),top3_rate:pct(top3,rows.length),priced:priced.length,virtual_stake_yen:100*priced.length,virtual_return_yen:returned,virtual_roi:pct(returned,100*priced.length)};
  }
  const grouped=rows=>Object.fromEntries(["S","A","B","C","unrated"].map(g=>[g,stats(rows.filter(r=>grade(r)===g))]));
  const rr=payload.races.filter(valid);
  const dates=[...new Set(rr.map(r=>r.date))].sort();
  const context=rr.filter(r=>r.entry_context_at_lock&&Date.parse(r.entry_context_at_lock.observed_at)<=Date.parse(r.locked_at));
  const flat=context.filter(r=>r.entry_context_at_lock.discipline==="flat");
  const byTrack={};for(const r of flat){const k=r.entry_context_at_lock.track_condition||"unknown";(byTrack[k]??=[]).push(r);}
  const weightOK=h=>Number.isFinite(h?.weight_kg)&&h.weight_kg>0;
  const complete=flat.filter(r=>{const h=r.entry_context_at_lock.horses;return Array.isArray(h)&&h.length===r.ranking.length&&new Set(h.map(x=>x.no)).size===h.length&&r.ranking.every(x=>h.some(y=>y.no===x.no&&weightOK(y)));});
  const weights=flat.flatMap(r=>Array.isArray(r.entry_context_at_lock.horses)?r.entry_context_at_lock.horses:[]);
  // Historical snapshots without quality counters remain unknown, never backfilled.
  const reasonKeys=["valid","source_blank","invalid_format","outside_screening_range"];
  const weightReasons=Object.fromEntries(reasonKeys.map(k=>[k,0]));
  let qualityRaces=0, qualityRows=0, legacyOrInvalidQualityRaces=0;
  for(const r of flat){
    const q=r.entry_context_at_lock.weight_quality, hs=r.entry_context_at_lock.horses;
    if(!q||!Array.isArray(hs)||!reasonKeys.every(k=>Number.isSafeInteger(q[k])&&q[k]>=0)||reasonKeys.reduce((s,k)=>s+q[k],0)!==hs.length||q.valid!==hs.filter(weightOK).length){legacyOrInvalidQualityRaces++;continue;}
    qualityRaces++;qualityRows+=hs.length;for(const k of reasonKeys)weightReasons[k]+=q[k];
  }

  return {version:"nar_priority_audit_v1",snapshot,source_updated_at:payload.updated_at||null,total_records:payload.races.length,eligible:rr.length,excluded:payload.races.length-rr.length,first_date:dates[0]||null,last_date:dates.at(-1)||null,confidence:grouped(rr),latest_day_confidence:grouped(rr.filter(r=>r.date===dates.at(-1))),context:{recorded_races:context.length,flat_races:flat.length,nonflat_excluded:context.length-flat.length,dates:[...new Set(context.map(r=>r.date))].sort(),by_track:Object.fromEntries(Object.entries(byTrack).map(([k,v])=>[k,stats(v)])),complete_weight_races:complete.length,horse_weight_records:weights.length,valid_horse_weight_records:weights.filter(weightOK).length,weight_quality:{races:qualityRaces,horse_rows:qualityRows,legacy_or_invalid_races:legacyOrInvalidQualityRaces,reasons:weightReasons}},limitations:["Retrospective descriptive audit only; no causal contribution, model changes, or prospective performance claims.","Confidence reconstructed using current UI thresholds and immutable pre-race odds; historical thresholds may differ.","Payouts from stored records, not independently reconciled; no refund adjustment. Excludes alternate results.","Track and carried weight context is diagnostic only; nonflat racing excluded from context subgroup analysis."]};
}
function selftest(){
  const r={id:"test",date:"2026-11-26",start_at:"2026-11-26T12:00:00+09:00",cutoff_at:"2026-11-26T11:45:00+09:00",predicted_at:"2026-11-26T11:40:00+09:00",locked_at:"2026-11-26T11:40:00+09:00",result:[1,2,3],ranking:[{no:1,win_probability:.6},{no:2,win_probability:.25},{no:3,win_probability:.15}],top3:[{no:1}],market_at_lock:{updated_at:"2026-11-26T11:39:00+09:00",horses:[{no:1,odds:1.5},{no:2,odds:4},{no:3,odds:6}]},payouts:{win:150},entry_context_at_lock:{observed_at:"2026-11-26T11:39:00+09:00",discipline:"flat",track_condition:"良",horses:[{no:1,weight_kg:55},{no:2,weight_kg:56},{no:3,weight_kg:null}]}};
  const checks=[
    [audit({races:[r]}).confidence.S.virtual_roi===150,"S and payout"],
    [audit({races:[{...r,market_at_lock:null}]}).confidence.B.races===1,"missing odds capped"],
    [audit({races:[{...r,locked_at:r.cutoff_at}]}).eligible===0,"late lock excluded"],
    [audit({races:[r,r]}).eligible===0,"duplicate excluded"],
    [audit({races:[r]}).context.complete_weight_races===0,"missing weight"],
    [audit({races:[r]}).context.weight_quality.legacy_or_invalid_races===1,"legacy unknown"],
    [audit({races:[{...r,entry_context_at_lock:{...r.entry_context_at_lock,weight_quality:{valid:2,source_blank:1,invalid_format:0,outside_screening_range:0}}}]}).context.weight_quality.reasons.source_blank===1,"new reasons counted"],
    [audit({races:[{...r,entry_context_at_lock:{...r.entry_context_at_lock,weight_quality:{valid:3,source_blank:0,invalid_format:0,outside_screening_range:0}}}]}).context.weight_quality.races===0,"inconsistent counters rejected"],
    [audit({races:[{...r,entry_context_at_lock:{...r.entry_context_at_lock,observed_at:r.start_at}}]}).context.recorded_races===0,"future context excluded"],
    [audit({races:[{...r,payouts:{}}]}).confidence.S.virtual_roi===null,"missing payout not loss"],
    [audit({races:[{...r,result_alternatives:[[1,3,2]]}]}).eligible===0,"alternate results excluded"]
  ];
  for(const [ok,label] of checks)if(!ok)throw Error(label);
  return checks.length;
}
if(require.main===module){
 const fs=require('node:fs');
 if(process.argv.includes('--selftest')){console.log('Passed '+selftest()+' checks');}
 else {const path=process.argv[2]||'data/auto/nar_predictions.json'; const result=audit(JSON.parse(fs.readFileSync(path,'utf8')),process.argv[3]||'local'); console.log(JSON.stringify(result,null,2));}
}
module.exports={audit,selftest};

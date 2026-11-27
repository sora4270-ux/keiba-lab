// Read-only NAR archive integrity audit. No prediction or purchase logic changes.
// Usage: node scripts/audit_nar_archive.cjs 2026-11-26 2026-11-27
// Self-test: node scripts/audit_nar_archive.cjs --selftest
"use strict";
function audit(data, dates) {
  if (!Array.isArray(data.races) || !Array.isArray(data.schedule)) throw new Error("Invalid archive");
  const result = [];
  for (const date of dates) {
    const races=data.races.filter(r=>r.date===date), schedule=data.schedule.filter(r=>r.date===date);
    const ids=new Set(races.map(r=>r.id));
    const out={date,scheduled:schedule.length,forecasts:races.length,missingForecasts:schedule.filter(r=>!ids.has(r.id)).length,duplicateIds:races.length-ids.size,settled:0,missingResult:0,invalidResult:0,late:0,unknownTiming:0,earlyOver30Minutes:0,finishMismatch:0,missingPayout:0,missingContext:0,missingWeightRaces:0,missingWeightQualityRaces:0,weightReasons:{valid:0,source_blank:0,invalid_format:0,outside_screening_range:0}};
    for(const r of races) {
      const t=Date.parse(r.predicted_at),c=Date.parse(r.cutoff_at);
      if(!Number.isFinite(t)||!Number.isFinite(c)) out.unknownTiming++;
      else if(t>=c) out.late++;
      else if(c-t>30*60000) out.earlyOver30Minutes++;
      const x=r.entry_context_at_lock;
      if(!x||!Array.isArray(x.horses))out.missingContext++;
      else {
        if(x.horses.some(h=>h.weight_kg==null))out.missingWeightRaces++;
        const keys=Object.keys(out.weightReasons);
        if(!keys.every(k=>Number.isInteger(x.weight_quality?.[k])&&x.weight_quality[k]>=0))out.missingWeightQualityRaces++;
        else for(const k of keys)out.weightReasons[k]+=x.weight_quality[k];
      }
      if(r.result==null){out.missingResult++;continue;}
      if(!Array.isArray(r.result)||r.result.length!==3||!r.result.every(n=>Number.isInteger(n)&&n>0)||new Set(r.result).size!==3){out.invalidResult++;continue;}
      out.settled++;
      if(!Array.isArray(r.finish_order)||r.finish_order.filter(h=>[1,2,3].includes(h.rank)).sort((a,b)=>a.rank-b.rank).map(h=>h.no).join(",")!==r.result.join(","))out.finishMismatch++;
      if(!["win","quinella","exacta","trio","trifecta"].every(k=>Number.isFinite(r.payouts?.[k])&&r.payouts[k]>0))out.missingPayout++;
    }
    result.push(out);
  }
  return result;
}
function selftest(){
 const d="2026-11-27", base={id:"a",date:d,predicted_at:d+"T10:00:00+09:00",cutoff_at:d+"T10:31:00+09:00",result:[1,2,3],finish_order:[{no:1,rank:1},{no:2,rank:2},{no:3,rank:3}],payouts:{win:100,quinella:100,exacta:100,trio:100,trifecta:100},entry_context_at_lock:{horses:[{weight_kg:null}],weight_quality:{source_blank:1}}};
 const r=audit({races:[base,{...base,predicted_at:base.cutoff_at,result:[1,1,2]},{...base,id:"b",predicted_at:null,result:null,entry_context_at_lock:null}],schedule:[{id:"a",date:d},{id:"c",date:d}]},[d])[0];
 const expected={duplicateIds:1,missingForecasts:1,settled:1,invalidResult:1,missingResult:1,late:1,unknownTiming:1,earlyOver30Minutes:1,finishMismatch:0,missingPayout:0,missingContext:1,missingWeightRaces:2,missingWeightQualityRaces:2};
 for(const [k,v] of Object.entries(expected))if(r[k]!==v)throw new Error(`${k}: ${r[k]} != ${v}`);
 const bad=audit({races:[{...base,finish_order:[],payouts:{}}],schedule:[]},[d])[0];
 if(bad.finishMismatch!==1||bad.missingPayout!==1)throw new Error("Missing data regression");
}
if(require.main===module){
 const args=process.argv.slice(2);
 if(args.length===1&&args[0]==="--selftest"){selftest();console.log("audit self-test passed");}
 else{
 if(!args.length||args.some(d=>!/^\d{4}-\d{2}-\d{2}$/.test(d)))throw new Error("Supply dates YYYY-MM-DD");
 const fs=require("node:fs"),path=require("node:path");
 const data=JSON.parse(fs.readFileSync(path.join(__dirname,"../data/auto/nar_predictions.json"),"utf8"));
 console.log(JSON.stringify(audit(data,[...new Set(args)]),null,2));
 }
}
module.exports={audit,selftest};

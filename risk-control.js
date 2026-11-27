/* Application-only loss controls. No purchase API exists. */
(function(root){
'use strict';
const yen=n=>Number.isSafeInteger(n)&&n>=0;
function validate(rows){
 if(!Array.isArray(rows))throw Error('記録形式が不正です');
 const ids=new Set();
 for(const r of rows){
  if(!r||typeof r.id!=='string'||!r.id||ids.has(r.id)||!['paper','actual'].includes(r.mode)||!yen(r.stake)||r.stake<100||r.stake%100||!yen(r.returned)||!yen(r.refund)||r.refund>r.stake||!['open','settled'].includes(r.status)||!Number.isFinite(Date.parse(r.at))||!/(Z|[+-]\d{2}:\d{2})$/.test(r.at)||typeof r.race!=='string'||!r.race|| (r.mode==='actual'&&(!r.receipt||typeof r.receipt!=='string')) || (r.status==='open'&&(r.returned||r.refund)))throw Error('購入記録に欠損・重複・不正な金額があります');
  ids.add(r.id);
 }
 return rows;
}
function day(at){return new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Tokyo',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(at));}
function assess(rows,limits,mode,now=Date.now(),requested=0,emergency=false){
 validate(rows);
 if(!['paper','actual'].includes(mode)||!yen(requested)||![limits.day,limits.month,limits.race].every(n=>yen(n)&&n>=100)||limits.race>limits.day||limits.day>limits.month)throw Error('上限は1レース≦日次≦月次の100円以上で設定してください');
 const today=day(now),month=today.slice(0,7);let daily=0,monthly=0,outstanding=0;
 for(const r of rows.filter(x=>x.mode===mode)){
  if(Date.parse(r.at)>now)throw Error('未来の購入記録があります');
  const loss=r.status==='open'?r.stake:Math.max(0,r.stake-r.returned-r.refund),d=day(r.at);
  if(r.status==='open'){outstanding+=r.stake;continue;}
  if(d===today)daily+=loss;
  if(d.slice(0,7)===month)monthly+=loss;
 }
 // Pending bets from previous periods remain reserved until explicitly settled.
 daily+=outstanding;monthly+=outstanding;
 const reasons=[];
 if(emergency)reasons.push('手動停止中');
 if(daily>=limits.day||daily+requested>limits.day)reasons.push('日次損失上限');
 if(monthly>=limits.month||monthly+requested>limits.month)reasons.push('月次損失上限');
 if(requested>limits.race)reasons.push('1レース上限');
 return {allowed:reasons.length===0,reasons,daily,monthly,outstanding,remaining:Math.max(0,Math.min(limits.day-daily,limits.month-monthly))};
}
function plan(rows,limits,request,{now=Date.now(),release=null,health=null,emergency=false}={}){
 const reasons=[];let budget;
 try{budget=assess(rows,limits,request.mode,now,request.stake,emergency);}catch(e){return {allowed:false,reasons:[e.message]};}
 if(!budget.allowed)reasons.push(...budget.reasons);
 // Release is deliberately closed until a separately reviewed production policy exists.
 if(request.mode==='actual')reasons.push('実資金運用は未承認');
 const h=health&&Date.parse(health.completed_at);
 if(!health||health.status!=='success'||!Number.isFinite(h)||h>now||now-h>5*60000)reasons.push('取得失敗・更新遅延');
 const race=request.race,quote=request.quote;
 const start=race&&Date.parse(race.start_at),cutoff=race&&Date.parse(race.cutoff_at),locked=race&&Date.parse(race.locked_at),predicted=race&&Date.parse(race.predicted_at),observed=quote&&Date.parse(quote.updated_at);
 if(![start,cutoff,locked,predicted,observed].every(Number.isFinite)||predicted>locked||locked>now||locked>=cutoff||cutoff!==start-15*60000||now>=cutoff||observed>locked||now-observed>5*60000)reasons.push('発走前確定・オッズ時刻に異常');
 if(!quote||!Array.isArray(quote.horses)||!quote.horses.length||quote.horses.some(x=>!Number.isInteger(x.no)||!Number.isFinite(x.odds)||x.odds<1)||new Set(quote.horses.map(x=>x.no)).size!==quote.horses.length)reasons.push('オッズ欠損・重複');
 if(!race||race.status==='draft'||race.result||!Array.isArray(race.ranking)||race.ranking.some(x=>!quote?.horses?.some(h=>h.no===x.no))||race.runner_status_verified!==true||race.has_withdrawal!==false)reasons.push('取消・出走状態が未確認');
 return {allowed:!reasons.length,reasons,budget};
}
const api={validate,assess,plan,day};if(typeof module!=='undefined')module.exports=api;else root.KeibaRisk=api;
})(globalThis);

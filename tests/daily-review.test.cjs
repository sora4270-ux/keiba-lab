'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const html=fs.readFileSync('index.html','utf8');
const slice=(a,b)=>html.slice(html.indexOf(a),html.indexOf(b,html.indexOf(a)));
const source=slice('function savedTrioList(r){','function trioTokens(tickets){')+slice('function resultReview(r){','function narPct(v){')+slice('function narReferenceWager(r,key){','function narPeriodRaces(records,period){')+slice('function roiStatistics(bets){','function recordResult(rec,top,payouts={})');
const api=new Function('esc','amount',source+';return {forecastQuality,forecastQualityHtml,reviewMetrics,dailyReviewHtml};')(x=>String(x),x=>String(x)+'円');
const r={ranking:[1,2,3].map(no=>({no})),top5:[1,2,3].map(no=>({no})),top3:[1,2,3].map(no=>({no})),tickets:[[1,2,3],[1,3,2]],trio_tickets:[[1,2,3]],result:[1,2,3],payouts:{trio:50,trifecta:100},predicted_at:'2026-11-08T12:00:00+09:00',cutoff_at:'2026-11-08T12:05:00+09:00',market_at_lock:{updated_at:'2026-11-08T11:59:00+09:00',horses:[1,2,3].map(no=>({no,odds:3}))},trifecta_plan:{candidate_mass:.5}};
assert.equal(api.forecastQuality(r).cautious,false);
assert.equal(api.forecastQuality({...r,trifecta_plan:{candidate_mass:.399}}).lowCoverage,true);
assert.equal(api.forecastQuality({...r,trifecta_plan:{candidate_mass:.4}}).lowCoverage,false);
const noSnap={...r,market_at_lock:null,market:r.market_at_lock};
assert.equal(api.forecastQuality(noSnap).missingMarket,true,'later display odds must not repair the pre-race audit');
assert.equal(api.forecastQuality({...r,market_at_lock:{...r.market_at_lock,updated_at:'2026-11-08T11:44:59+09:00'}}).staleMarket,true);
assert.equal(api.forecastQuality({...r,market_at_lock:{...r.market_at_lock,updated_at:'2026-11-08T12:01:00+09:00'}}).staleMarket,true);
const before=JSON.stringify(r);
const m=api.reviewMetrics([r,{...r,payouts:{}},{...r,result:null}],'trifecta');
assert.equal(m.hits,2);assert.equal(m.priced,1);assert.equal(m.stats.spent,200);assert.equal(m.stats.returned,100);assert.equal(m.losingHits,1);
assert.match(api.dailyReviewHtml([r]),/的中でも赤字 1R/);
assert.equal(JSON.stringify(r),before,'review must not mutate historical forecasts');
// Use the real saved ledger as a regression fixture, with no odds/results rewrite.
const data=JSON.parse(fs.readFileSync('data/auto/nar_predictions.json','utf8'));
const today=data.races.filter(r=>r.date==='2026-11-08');
if(today.length===47){const t=api.reviewMetrics(today,'trifecta');assert.equal(t.hits,22);assert.equal(t.stats.spent,107100);assert.equal(t.stats.returned,60630);assert.equal(t.losingHits,12);}
const nov9=data.races.filter(r=>r.date==='2026-11-09');
if(nov9.length===48){
 const review=api.dailyReviewHtml(nov9);
 assert.match(review,/候補5頭から漏れ 33R/);
 assert.match(review,/6位までで全頭 7R ／ 7位までで全頭 14R/);
 assert.match(review,/単勝オッズ不足 6R：三連複 0\/6R ／ 三連単 0\/6R/);
}
const nov10=data.races.filter(r=>r.date==='2026-11-10');
if(nov10.length===59){
 const review=api.dailyReviewHtml(nov10);
 assert.match(review,/選択条件の反省：59R/);
 assert.match(review,/三連複5頭BOXの候補漏れ 37R/);
 assert.match(review,/三連単 的中 14\/59R/);
 assert.equal(api.reviewMetrics(nov10,'trifecta').stats.spent,130500);
}
console.log('PASS: pre-race quality, stale/future odds, missing payouts, losing hits and immutable daily ledger');

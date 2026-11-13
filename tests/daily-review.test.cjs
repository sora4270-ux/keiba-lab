'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const html=fs.readFileSync('index.html','utf8');
const slice=(a,b)=>html.slice(html.indexOf(a),html.indexOf(b,html.indexOf(a)));
const source=slice('function savedTrioList(r){','function trioTokens(tickets){')+slice('function budgetTicketLists(','function refreshBudgetTickets(')+slice('function resultReview(r){','function narPct(v){')+slice('function narReferenceWager(r,key){','function narPeriodRaces(records,period){')+slice('function roiStatistics(bets){','function recordResult(rec,top,payouts={})');
const api=new Function('esc','amount',source+';return {forecastQuality,forecastQualityHtml,reviewMetrics,dailyReviewHtml,budgetTicketsHtml};')(x=>String(x),x=>String(x)+'円');
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
const nov11=data.races.filter(r=>r.date==='2026-11-11'&&r.result);
if(nov11.length===48){
 const review=api.dailyReviewHtml(nov11);
 assert.match(review,/1レースの予算別成績（48R）/);
 assert.match(review,/500円<\/th><td>14\/48R ／ 52\.2%/);
 assert.match(review,/<td>4\/48R ／ 36\.6%/);
 assert.match(review,/3頭は登場・同じ組なし 17R/);
 assert.match(review,/3頭組あり・着順違い 10R/);
}
const box=Array.from({length:10},(_,i)=>[1,2,4+i]);
const field=[r.result,...box.slice(0,9)];
const review=api.dailyReviewHtml([{...r,trio_tickets:box,trio_full_field_tickets:field}]);
assert.match(review,/上位5頭BOX 0\/1R ／ 回収率 0\.0% ／ 全出走馬から選ぶ10点 1\/1R ／ 回収率 5\.0%/);
assert.match(review,/三連複の予算別比較（1R）/);
assert.match(review,/300円<\/th><td>0\/1R ／ 0\.0%.*?<td>1\/1R ／ 16\.7%/);
assert.match(api.budgetTicketsHtml(box,r.tickets,r.ranking,field),/value="fieldTrio"/);
assert.doesNotMatch(api.budgetTicketsHtml(box,r.tickets,r.ranking),/value="fieldTrio"/);
assert.doesNotMatch(api.dailyReviewHtml([{...r,payouts:{},trio_tickets:box,trio_full_field_tickets:field}]),/三連複の予算別比較/);
const trifectaReview=api.dailyReviewHtml([{...r,trifecta_diversified_tickets:[[2,1,3],[3,1,2]]}]);
assert.match(trifectaReview,/従来の確率順 1\/1R ／ 回収率 50\.0% ／ 3頭の組を広げる方式 0\/1R ／ 回収率 0\.0%/);
console.log('PASS: pre-race quality, stale/future odds, missing payouts, losing hits and immutable daily ledger');
const nov13=data.races.filter(r=>r.date==='2026-11-13'&&r.result);
if(nov13.length===46){
 const publishedReview=api.dailyReviewHtml(nov13);
 assert.match(publishedReview,/三連単の予算別比較（40R）/);
 assert.match(publishedReview,/300円<\/th><td>9\/40R ／ 回収率 122\.0%.*?<td>9\/40R ／ 回収率 122\.0%/);
 assert.match(publishedReview,/1000円<\/th><td>13\/40R ／ 回収率 62\.9%.*?<td>13\/40R ／ 回収率 62\.9%/);
}
assert.match(api.budgetTicketsHtml(box,r.tickets,r.ranking,field,[[2,1,3]]),/value="diversifiedTrifecta"/);
assert.doesNotMatch(api.budgetTicketsHtml(box,r.tickets,r.ranking,field),/value="diversifiedTrifecta"/);
assert.doesNotMatch(api.dailyReviewHtml([{...r,payouts:{},trifecta_diversified_tickets:r.tickets}]),/三連単の予算別比較/);

'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');

const html = fs.readFileSync('index.html','utf8');
function snippet(start,end) {
  const a=html.indexOf(start), b=html.indexOf(end,a);
  assert.ok(a>=0 && b>a, 'Source function not found: '+start);
  return html.slice(a,b);
}
const source=[
  snippet('function resultMatches(rec){','function optionalPayout(v,label){'),
  snippet('function payoutValue(r,key){','function recordResult(rec,top,payouts={})'),
  snippet('function savedTrioList(r){','function trioTokens(tickets){'),
  snippet('function narReferenceWager(r,key){','function narPeriodRaces(records,period){')
].join('\n')+'\n({resultMatches,payoutValue,referenceWager,roiStatistics,roiLabel,completeBasket,savedTrioList,narReferenceWager})';
const api=vm.runInNewContext(source,{console});

const payouts={win:200,quinella:500,exacta:750,trio:2000,trifecta:10000};
const nar={
  result:[1,2,3],top3:[{no:1},{no:2},{no:3}],
  trio_tickets:[[1,2,3]], tickets:[[1,2,3],[1,3,2]], payouts
};
const single=api.narReferenceWager(nar,'trifecta');
assert.equal(single.spent,200);
assert.equal(single.returned,10000);
assert.equal(api.narReferenceWager(nar,'trio').spent,100);
assert.equal(api.narReferenceWager(nar,'trio_main').spent,100);
assert.equal(api.narReferenceWager(nar,'win').returned,200);
const combined=api.completeBasket([nar],api.narReferenceWager);
assert.equal(combined.races,1);
assert.equal(combined.stats.spent,600);
assert.equal(combined.stats.returned,13450);
assert.ok(Math.abs(combined.stats.rate-(13450/600*100))<0.001);
const experimental={...nar,trio_value:{tickets:[[1,2,3],[1,2,4],[1,3,4],[2,3,4]]}};
assert.equal(api.narReferenceWager(experimental,'trio_value').spent,400);
assert.equal(api.narReferenceWager(experimental,'trio_value').returned,2000);
assert.equal(api.narReferenceWager({...experimental,trio_value:{tickets:[]}},'trio_value'),null);
assert.equal(api.narReferenceWager(nar,'trio_value'),null);
assert.equal(api.completeBasket([experimental],api.narReferenceWager).stats.spent,600,
  'Experimental wagers must NOT be mixed into the existing 5-type basket');
const noPay={...nar,payouts:{...payouts,trio:null}};
assert.equal(api.completeBasket([noPay],api.narReferenceWager).races,0);
assert.equal(api.narReferenceWager(noPay,'trio'),null);
const miss={...nar,result:[3,2,1]};
assert.equal(api.narReferenceWager(miss,'win').returned,0);
assert.equal(api.narReferenceWager(miss,'trio').returned,2000);
assert.equal(api.narReferenceWager(miss,'trifecta').returned,0);
const jra={result:[1,2,3],top3:[1,2,3],tickets:[[1,2,3],[1,3,2]],betCount:2,payouts};
assert.equal(api.referenceWager(jra,'trifecta').spent,200);
assert.equal(api.referenceWager(jra,'trio').returned,2000);
assert.equal(api.completeBasket([jra],api.referenceWager).stats.spent,600);
assert.equal(api.roiStatistics([]).rate,null);
assert.equal(api.roiLabel(api.roiStatistics([])),'—');
const historic={...nar,trio_tickets:undefined};
assert.equal(api.savedTrioList(historic).length,1);
assert.equal(api.narReferenceWager(historic,'trio').spent,100);

const publicData=JSON.parse(fs.readFileSync('data/auto/nar_predictions.json','utf8'));
for(const race of publicData.races) {
  const result=api.completeBasket([race],api.narReferenceWager);
  assert.ok(result.stats.spent>=0 && result.stats.returned>=0);
  if(result.races)assert.ok(Number.isFinite(result.stats.rate));
}
console.log('PASS ROI: 100-yen stakes, confirmed payouts, trifecta/trio, missing payouts, 5-type combined return');

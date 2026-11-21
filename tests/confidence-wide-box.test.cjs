'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs');
const html=fs.readFileSync('index.html','utf8');
function slice(a,b){const i=html.indexOf(a);assert(i>=0,'missing '+a);const j=html.indexOf(b,i);assert(j>i,'missing '+b);return html.slice(i,j);}
const source=slice('function wideBoxNumbers(', 'function narWideBoxWager(');
const api=new Function(source+';return {wideBoxNumbers,wideBoxTickets,confidenceWideNumbers,confidenceWideTickets,narWideBoxTickets};');
const {confidenceWideNumbers,confidenceWideTickets,wideBoxTickets}=api();
const ranks=Array.from({length:8},(_,i)=>({no:i+1}));
assert.deepEqual(confidenceWideNumbers(ranks,{grade:'S'}),[1,2,3,4,5]);
for(const grade of ['A','B','C'])assert.deepEqual(confidenceWideNumbers(ranks,{grade}),[2,3,4,5,6]);
assert.equal(confidenceWideTickets(ranks,{grade:'S'}).length,10);
assert.equal(confidenceWideTickets(ranks,{grade:'A'}).length,10);
assert.deepEqual(confidenceWideNumbers(ranks.slice(0,5),{grade:'B'}),[]);
assert.deepEqual(confidenceWideTickets(ranks.slice(0,5),{grade:'B'}),[]);
assert.deepEqual(confidenceWideTickets(ranks,{grade:'unknown'}),[]);
assert.deepEqual(confidenceWideTickets([{no:1},{no:2},{no:2},{no:4},{no:5},{no:6}],{grade:'S'}),[]);
assert.equal(wideBoxTickets([2,3,4,5,6]).length,10);
console.log('Confidence wide BOX selection tests passed');

const source=html.slice(html.indexOf('function betDecisionGuide('),html.indexOf('function forecastDetails('));
assert(source.includes('confidenceOverride'), 'display must accept frozen NAR confidence');
assert(source.includes('key===\'wide\'?wideTickets'), 'wide card must show confidence-tier tickets');
const nar=html.slice(html.indexOf('function narWideStrategyWager('),html.indexOf('function narPeriodRaces('));
assert(nar.includes("mode==='confidence'"), 'historical comparison must include confidence BOX');
const warnings=html.slice(html.indexOf('function forecastQualityHtml('),html.indexOf('function reviewMetrics('));
assert(warnings.includes('ばんえい専用'), 'Banei races require an explicit model-quality warning');
assert(warnings.includes('feature_validation'), 'missing observed features must be disclosed');
console.log('UI consistency and Banei quality warning checks passed');

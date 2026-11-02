'use strict';
const fs = require('node:fs');
const assert = require('node:assert/strict');
const html = fs.readFileSync('index.html', 'utf8');
const between = (from, to) => {
  const start = html.indexOf(from);
  const finish = html.indexOf(to, start);
  assert.ok(start >= 0 && finish > start, 'Missing test section: '+from);
  return html.slice(start, finish);
};
const lock = between('const FORECAST_LOCK_MINUTES=10;', "const LEDGER_KEY=");
const jra = between('function jraDateTime(', 'function jraValidRaces(');
const snapshot = between('function makeSnapshot(', 'function addPredictions(');
const save = between('function addPredictions(', 'function batchPredict(');
const source = [
  'let ledger = [];',
  "const JRA_VENUES = new Set(['東京','中山','京都','阪神','中京','新潟','福島','小倉','札幌','函館']);",
  'const validateRace = ()=>{};',
  'const oddsOnly = ()=>true;',
  "const raceKey = r => r.date+'|'+r.id;",
  'const model = {trained:false};',
  "const probs = ()=>{throw Error('not needed for odds-only test');};",
  "const $ = id => id==='budget'?{value:'1000'}:{value:'main',checked:false};",
  'const exactCombinations = ()=>[];',
  'const chooseTickets = ()=>[];',
  'const persistLedger = ()=>true;',
  'const renderLedger = ()=>{};',
  lock, jra, snapshot, save,
  'return {assertForecastOpen,forecastCutoffMillis,jraDateTime,makeSnapshot,addPredictions,ledger};'
].join('\n');
const api = new Function(source)();
const start='2026-11-07T15:40:00+09:00';
const cutoff=Date.parse('2026-11-07T15:30:00+09:00');
assert.equal(api.forecastCutoffMillis(start),cutoff);
assert.doesNotThrow(()=>api.assertForecastOpen(start,cutoff-1));
assert.throws(()=>api.assertForecastOpen(start,cutoff),/10分前/);
assert.throws(()=>api.assertForecastOpen(start,cutoff+1),/10分前/);
assert.throws(()=>api.assertForecastOpen(''),/発走日時は必須/);
assert.throws(()=>api.assertForecastOpen('2026-11-07T15:40:00'),/発走日時は必須/);
const valid={id:'future-R11',name:'実レース',venue:'東京',race_no:11};
api.jraDateTime({...valid,date:'2099-11-07',start_at:'2099-11-07T15:40:00+09:00'});
const isoAt=millis=>new Date(millis).toISOString().slice(0,19)+'Z';
const jstDate=millis=>new Date(millis).toLocaleDateString('sv-SE',{timeZone:'Asia/Tokyo'});
const now=Date.now();
const horses=[
  {no:1,name:'Horse A',odds:2.5},
  {no:2,name:'Horse B',odds:5.0},
  {no:3,name:'Horse C',odds:9.5}
];
const race=(delta,id='test')=>({...valid,id,date:jstDate(now+delta),start_at:isoAt(now+delta),horses});
assert.throws(()=>api.makeSnapshot(race(9*60*1000),'licensed feed'),/10分前/);
assert.throws(()=>api.makeSnapshot({...race(11*60*1000),start_at:''},'licensed feed'),/発走日時は必須/);
const available=api.makeSnapshot(race(15*60*1000),'licensed feed');
assert.equal(available.cutoffAt,new Date(Date.parse(available.startAt)-600000).toISOString());
assert.ok(Date.parse(available.lockedAt)<Date.parse(available.cutoffAt));
api.addPredictions([available]);
assert.equal(api.ledger.length,1);
assert.throws(()=>api.makeSnapshot(race(15*60*1000),'licensed feed'),/上書き不可/);
assert.throws(()=>api.addPredictions([{
  ...available,key:'late|future',startAt:isoAt(now+9*60*1000)
}]),/10分前/);
assert.equal(api.ledger.length,1);
console.log('PASS: T-10 boundary, JRA validation, manual/feed snapshot and final persistence guard');

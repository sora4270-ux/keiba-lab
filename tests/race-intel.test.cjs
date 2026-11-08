'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const render = new Function(fs.readFileSync('race-intel.js', 'utf8') + '\nreturn raceInsightHtml;')();

// Market popularity is independent from prediction order.
const nar = render({
  ranking: [
    {no: 6, name:'本命馬', win_probability:0.42},
    {no: 2, name:'人気馬', win_probability:0.28},
    {no: 4, name:'穴馬', win_probability:0.12}
  ],
  market: {horses:[
    {no: 6, odds:6.4, popularity:3},
    {no: 2, odds:2.5, popularity:1},
    {no: 4, odds:4.5, popularity:2}
  ], updated_at:'2026-11-02T14:05:00+09:00'}
}, 'NAR');
assert.match(nar, /2\.5倍/);
assert.match(nar, /6\.4倍/);
assert.match(nar, /1番人気/);
assert.match(nar, /3番人気/);
assert.match(nar, /ペース判定不可/);
assert.ok(nar.indexOf('◎ 予想上位') < nar.indexOf('★ 人気順'));

// Supplied running styles make a clearly qualified pace projection.
const jra = render({runners:[
  {no:8,name:'先行A',odds:4.2,win_probability:0.2,runningStyle:'先行'},
  {no:2,name:'逃げA',odds:3.1,win_probability:0.4,runningStyle:'逃げ'},
  {no:6,name:'逃げB',odds:5.3,win_probability:0.3,runningStyle:'逃げ'},
  {no:1,name:'追込A',odds:17.1,win_probability:0.1,runningStyle:'追込'}
]}, 'JRA');
assert.match(jra, /やや速め/);
assert.match(jra, /2番・6番/);
assert.match(jra, /全頭の人気順と予想順位を見る/);
assert.ok(jra.indexOf('2番</b> 逃げA') < jra.indexOf('6番</b> 逃げB'));

// A saved pre-lock snapshot must display for previews created before the fix.
const historicPreview = render({
  ranking: [
    {no: 8,name: '予想本命',win_probability:.6},
    {no: 2,name: 'オッズ最人気',win_probability:.3}
  ],
  market_at_lock: {horses:[
    {no:8,odds:7.8,popularity:2},
    {no:2,odds:2.1,popularity:1}
  ],updated_at:'2026-11-04T11:18:22+09:00'}
},'NAR');
assert.match(historicPreview,/2\.1倍/);
assert.match(historicPreview,/1番人気/);
assert.match(historicPreview,/予想時点の保存値/);

// An incomplete live update must not hide previously observed odds.
const mixedMarket = render({
  ranking: [{no: 8, name:'予想本命'}, {no: 2, name:'人気馬'}, {no: 3, name:'オッズなし'}],
  market_at_lock: {horses:[{no:8, odds:7.8, popularity:2}], updated_at:'2026-11-04T11:18:22+09:00'},
  market: {horses:[{no:2, odds:2.2}], updated_at:'2026-11-04T11:20:00+09:00'}
}, 'NAR');
assert.match(mixedMarket, /7\.8倍（保存値）/);
assert.match(mixedMarket, /2\.2倍/);
assert.doesNotMatch(mixedMarket, /1番人気/);

// Missing odds must never be replaced with imagined odds.
const missing = render({top3:[{no:1,name:'オッズ不明',win_probability:.3}]},'NAR');
assert.match(missing, /単勝オッズ未取得/);
assert.doesNotMatch(missing, /1\.0倍/);

// Old JRA entries (numeric top3) still render safely.
const legacy = render({top3:[4,2,1],horseNos:[1,2,4],horseNames:['A','B','D']},'JRA');
assert.match(legacy,/4番<\/b> D/);

// Horse names are escaped rather than inserted as live HTML.
const unsafe = render({ranking:[{no:1,name:'<img src=x onerror=evil()>',win_probability:.8}]},'NAR');
assert.match(unsafe,/&lt;img/);
assert.doesNotMatch(unsafe,/<img/);

// Refreshing a subset of JRA quotes must not erase original saved odds or
// silently calculate a popularity ranking from mixed observation times.
const jraPartial = render({
  runners: [
    {no:1,name:'保存本命',odds:3.5,win_probability:.5},
    {no:2,name:'更新対象',odds:9.0,win_probability:.3},
    {no:3,name:'保存穴馬',odds:18.0,win_probability:.2}
  ],
  market:{horses:[{no:2,odds:6.2}],updated_at:'2026-11-08T11:25:00+09:00'},
  createdAt:'2026-11-08T10:55:00+09:00'
},'JRA');
assert.match(jraPartial,/6\.2倍/);
assert.match(jraPartial,/3\.5倍（保存値）/);
assert.match(jraPartial,/18\.0倍（保存値）/);
assert.doesNotMatch(jraPartial,/1番人気/);

// The odds-only paste parser accepts JRA-style full-width number text,
// rejects unknown horses and duplicated entries without writing data.
const html=fs.readFileSync('index.html','utf8');
const parseStart=html.indexOf('function parseJraOddsPaste(');
const parseEnd=html.indexOf('function renderJraOddsOptions(',parseStart);
assert.ok(parseStart>0&&parseEnd>parseStart);
const parseJraOddsPaste=new Function(html.slice(parseStart,parseEnd)+';return parseJraOddsPaste;')();
const knownNumbers=new Set([1,2,3]);
assert.deepEqual([...parseJraOddsPaste('１番　２．６倍\n2,38.6',knownNumbers)],[[1,2.6],[2,38.6]]);
assert.throws(()=>parseJraOddsPaste('4 2.6',knownNumbers),/保存済み出走馬/);
assert.throws(()=>parseJraOddsPaste('1 2.6\n1 3.4',knownNumbers),/重複/);
assert.throws(()=>parseJraOddsPaste('1 0.5',knownNumbers),/1\.0/);
console.log('PASS: race pace, predictions, win odds, market popularity and XSS');

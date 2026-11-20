'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const html=fs.readFileSync('index.html','utf8');
const slice=(a,b)=>html.slice(html.indexOf(a),html.indexOf(b,html.indexOf(a)));
const esc=x=>String(x).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('"','&quot;');
const api=new Function('esc','narPct','narResultOrders',
 slice('function forecastMarks(', 'function compactBetsHtml(')+
 slice('function forecastMarkReviewHtml(', 'function dailyReviewHtml(')+
 ';return {forecastMarks,forecastPicksHtml,forecastExtraCandidatesHtml,forecastMarkReviewHtml};')
 (esc,x=>x.toFixed(1)+'%',r=>r.result_alternatives||[r.result]);
const top=Array.from({length:7},(_,i)=>({no:i+1,name:i===3?'<script>':'馬'+(i+1),win_probability:.1}));
const before=JSON.stringify(top);
assert.deepEqual(api.forecastMarks(top).map(x=>[x.mark,x.role]),[['◎','本命'],['○','対抗'],['▲','単穴'],['☆','注'],['△','連下']]);
const rendered=api.forecastPicksHtml(top,()=>'<odds>');
assert.match(rendered,/☆ 注/);assert.match(rendered,/△ 連下/);assert.doesNotMatch(rendered,/<script>|<odds>/);
assert.match(rendered,/&lt;script>/);assert.doesNotMatch(rendered,/7番/);
assert.equal(api.forecastMarks([top[0],top[0],{no:null},top[1]]).length,2);
assert.equal(api.forecastMarks(null).length,0);
assert.match(api.forecastPicksHtml([]),/未記録/);
assert.equal(api.forecastMarks(top.slice(0,3)).length,3,'do not invent missing fourth and fifth picks');
const extra=api.forecastExtraCandidatesHtml(top,top,[[1,6,7]],[[7,1,6]]);
assert.match(extra,/6番 馬6/);assert.match(extra,/7番 馬7/);assert.doesNotMatch(extra,/1番 馬1/);
assert.equal((extra.match(/6番/g)||[]).length,1);
const r={top5:top.slice(0,5),result:[1,4,6]};
const review=api.forecastMarkReviewHtml([r,{top3:top.slice(0,3),result:[2,1,3]},{result:[1,2,3]}]);
assert.match(review,/◎ 本命<\/th><td>1\/2R（50.0%）<\/td><td>2\/2R（100.0%）/);
assert.match(review,/☆ 注<\/th><td>0\/1R（0.0%）<\/td><td>1\/1R（100.0%）/);
assert.match(review,/印外の馬が3着内：1\/2R ／ 印未記録：1R/);
const deadheat=api.forecastMarkReviewHtml([{...r,result_alternatives:[[1,4,6],[1,4,5]]}]);
assert.match(deadheat,/△ 連下<\/th><td>0\/1R（0.0%）<\/td><td>1\/1R（100.0%）/);
assert.equal(JSON.stringify(top),before,'marks and review must not reorder the frozen forecast');
assert.match(html,/保存時の予想印/);
assert.match(html,/mode==='results'\?wagers\+forecastDetails\('保存時の予想印'/);
console.log('PASS: five roles, extra ticket horses, escaped content, incomplete history, dead heats and immutable forecasts');

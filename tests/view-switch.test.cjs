'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const html = fs.readFileSync('index.html','utf8');
for(const id of ['nar-view-mode','jra-view-mode','nar-results-summary','jra-results-summary','nar-list-title']){
  assert.ok(html.includes('id="'+id+'"'), 'Missing result/prediction view control: '+id);
}
const start=html.indexOf('function forecastResultRows(');
const end=html.indexOf('\nlet narViewedData=',start);
assert.ok(start>=0&&end>start,'Reusable forecast/result filter missing');
const filter=new Function(html.slice(start,end)+'\nreturn forecastResultRows;')();
const rows=[
 {id:'before',result:null},
 {id:'after',result:[1,2,3]},
 {id:'partial',result:[1,2]},
 {id:'bad',result:'complete'}
];
assert.equal(filter(rows,'predictions').length,4);
assert.deepEqual(filter(rows,'results').map(r=>r.id),['after']);
assert.equal(filter([], 'results').length,0);
assert.ok(html.includes("$('nar-results-summary').hidden=mode!=='results'"));
assert.ok(html.includes("$('jra-results-summary').hidden=mode!=='results'"));
assert.ok(html.includes("const shown=mode==='results'?finished.slice(0,60):"));
assert.ok(html.includes("const displayed=forecastResultRows(records,mode)"));
assert.ok(html.includes("const mode=$('nar-view-mode').value"));
assert.ok(html.includes("const mode=$('jra-view-mode').value"));
assert.ok(html.includes("const FORECAST_LOCK_MINUTES=15;"));
console.log('PASS: NAR and JRA forecast/result mode selection and result-only filtering');

const resultTable=new Function('esc',html.slice(html.indexOf('function resultOrderHtml('),html.indexOf('function trioTokens('))+';return resultOrderHtml;')(String);
const detail=resultTable({
 result:[3,1,2],finish_order:[{no:3,rank:1},{no:1,rank:2},{no:2,rank:3},{no:4,rank:4}],
 ranking:[{no:1,name:'A'},{no:3,name:'C'}],
 market:{horses:[{no:3,odds:7.5}]},market_at_lock:{horses:[{no:1,odds:2.8}]}
});
assert.match(detail, /1着<\/td><td>3番 C<\/td><td>7\.5倍<\/td><td>2位/);
assert.match(detail, /2着<\/td><td>1番 A<\/td><td>2\.8倍.*予想時.*<\/td><td>1位/);
assert.match(detail, /3着<\/td><td>2番 <\/td><td>未取得<\/td><td>未記録/);
assert.ok(detail.includes('全着順を見る')&&detail.includes('4着'));

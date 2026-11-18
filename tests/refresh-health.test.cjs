'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs');
const html=fs.readFileSync('index.html','utf8');
const source=html.slice(html.indexOf('function narHealthText('),html.indexOf('async function narHealthRefresh('));
const text=new Function(source+';return narHealthText;')();
const now=Date.parse('2026-11-18T12:00:00+09:00');
const record={schema_version:1,status:'success',completed_at:new Date(now).toISOString(),last_attempt_at:new Date(now-1000).toISOString(),last_success_at:new Date(now).toISOString(),consecutive_failures:0,content_changed:false,odds_status:'available'};
assert.match(text(record,now),/取得成功・データ変更なし/);
assert.match(text({...record,content_changed:true},now),/取得成功・データ変更あり/);
assert.match(text({...record,status:'failed',consecutive_failures:2},now),/取得失敗・連続 2回/);
assert.match(text({...record,odds_status:'unavailable'},now),/オッズは未取得/);
assert.match(text({...record,completed_at:new Date(now-31*60000).toISOString()},now),/30分以上/);
assert.doesNotMatch(text({...record,completed_at:'2026-11-17T12:00:00+09:00'},Date.parse('2026-11-18T06:10:00+09:00')),/30分以上/);
assert.match(text(record,Date.parse('2026-11-19T02:00:00+09:00')),/時間外/);
assert.doesNotMatch(text(record,Date.parse('2026-11-19T02:00:00+09:00')),/30分以上/);
assert.match(text(null,now),/未計測/);
assert.match(text({...record,completed_at:'bad'},now),/未計測/);
// Exercise the real fetch/display path independently of prediction fetching.
const refreshSource=html.slice(html.indexOf('async function narHealthRefresh('),html.indexOf('let narFetching='));
const element={textContent:''};
let response={ok:true,json:async()=>record},url='';
const refresh=new Function('$','fetch','NAR_AUTO_URL','narHealthText',refreshSource+';return narHealthRefresh;')(
 ()=>element,async u=>{url=u;return response;},'https://example.test/nar_predictions.json',text);
(async()=>{
 await refresh();assert.match(url,/nar_health.json\?v=/);assert.match(element.textContent,/取得成功/);
 response={ok:false};await refresh();assert.match(element.textContent,/成功・失敗は未確認/);
 response={ok:true,json:async()=>({...record,status:'failed',consecutive_failures:3})};
 await refresh();assert.match(element.textContent,/連続 3回/);
 console.log('PASS: refresh health status, freshness, off-hours and independent fetch failure');
})().catch(e=>{console.error(e);process.exitCode=1;});

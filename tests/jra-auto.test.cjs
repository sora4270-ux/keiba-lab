'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');

const python = fs.readFileSync('scripts/update_jra.py','utf8');
const workflow = fs.readFileSync('.github/workflows/jra-auto.yml','utf8');
const html = fs.readFileSync('index.html','utf8');
const stub = JSON.parse(fs.readFileSync('data/auto/jra_predictions.json','utf8'));

assert.equal(stub.status,'not_configured');
assert.deepEqual(stub.races,[]);
assert.ok(python.includes('JRA_PUBLICATION_RIGHTS_CONFIRMED'),'publication rights required');
assert.ok(python.includes('if not feed_url or not permitted:'),'no unlicensed automatic access');
assert.ok(python.includes('class BlockRedirect'),'no redirect credentials leaks');
assert.ok(python.includes('FORECAST_LOCK_BEFORE_START') || python.includes('CUT_OFF = dt.timedelta(minutes=15)'),'T-15 lock');
assert.ok(python.includes('if saved_time >= cutoff:'),'no retrospective prediction');
assert.ok(python.includes('entry.get("confirmed") is not True'),'reject preliminary results');
assert.ok(workflow.includes('JRA_LICENSED_FEED_URL'));
assert.ok(workflow.includes('JRA_PUBLICATION_RIGHTS_CONFIRMED'));
assert.ok(workflow.includes("cron: '*/5"),'scheduled refresh');
assert.ok(html.includes('id="jra-center"'),'JRA UI still available');
console.log('PASS: licensed JRA ingestion guard, no retroactive predictions, official results and scheduler');

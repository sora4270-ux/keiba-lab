'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const http = require('node:http');
const path = require('node:path');
const { chromium } = require('playwright');

async function run() {
  const root=process.cwd();
  const today=new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Tokyo'});
  const schedule=[4,5].map((n,i)=>({
    id:'ui-smoke-'+n,date:today,venue:'園田',race_no:n,
    start_at:new Date(Date.now()+(i+2)*3600000).toISOString()
  }));
  const mock={schema_version:1,updated_at:new Date().toISOString(),races:[],schedule,
    summary:{predicted:0,settled:0,pending:0}};
  const server=http.createServer((req,res)=>{
    const url=new URL(req.url,'http://127.0.0.1');
    const requested=path.resolve(root,'.'+decodeURIComponent(url.pathname));
    if(requested!==root&&!requested.startsWith(root+path.sep)){
      res.writeHead(403);res.end('Forbidden');return;
    }
    const file=requested===root?path.join(root,'index.html'):requested;
    fs.readFile(file,(err,buf)=>{
      if(err){res.writeHead(404);res.end('Not found');return;}
      const ext=path.extname(file);
      const contentType=ext==='.html'?'text/html; charset=utf-8':ext==='.js'?'text/javascript; charset=utf-8':ext==='.json'?'application/json':ext==='.webmanifest'?'application/manifest+json':'application/octet-stream';
      res.writeHead(200,{'Content-Type':contentType,'Cache-Control':'no-store'});res.end(buf);
    });
  });
  await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
  let browser;
  try {
    browser=await chromium.launch({headless:true});
    const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    const errors=[];
    page.on('pageerror',err=>errors.push(err.message));
    await page.route('**/data/auto/nar_predictions.json*',route=>route.fulfill({
      status:200,contentType:'application/json',body:JSON.stringify(mock)
    }));
    await page.goto('http://127.0.0.1:'+server.address().port+'/',{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.querySelector('#nar-count')?.textContent?.includes('開催情報'),{timeout:15000});
    assert.equal(await page.locator('.quick-link').count(),4,'home shortcuts');
    assert.ok((await page.locator('#quick-live-summary').innerText()).includes('開催情報 2R'),'summary includes schedule');
    assert.ok((await page.locator('#quick-next-race').innerText()).includes('発走まで約'),'next-race countdown shown');
    assert.ok(await page.locator('#quick-refresh').isVisible(),'manual refresh is available');
    assert.equal(await page.locator('.mobile-dock [data-jump="nar"][data-display="predictions"]').getAttribute('aria-current'),'page','NAR prediction is the initial active menu');
    assert.equal(await page.locator('.mobile-dock button').count(),5,'mobile bottom navigation');
    assert.ok(await page.locator('.mobile-dock').isVisible(),'bottom navigation visible on phone');
    assert.ok((await page.locator('#quick-next-race').innerText()).includes('発走予定'),'next race preview');

    await page.locator('#nar-view-date').selectOption('all');
    assert.ok((await page.locator('#nar-races').innerText()).includes('園田 4R'));
    assert.ok((await page.locator('#nar-races').innerText()).includes('園田 5R'));
    await page.locator('#nar-view-number').selectOption('4');
    assert.ok((await page.locator('#nar-races').innerText()).includes('園田 4R'));
    assert.ok(!(await page.locator('#nar-races').innerText()).includes('園田 5R'),'race-number filter');

    await page.locator('.quick-link[data-jump="nar"][data-display="results"]').click();
    assert.equal(await page.locator('#nar-view-mode').inputValue(),'results','NAR result mode');
    assert.equal(await page.locator('.mobile-dock [data-jump="nar"][data-display="results"]').getAttribute('aria-current'),'page','active menu follows result tab');
    assert.equal(await page.locator('[data-mode-select="nar-view-mode"] [data-mode="results"]').getAttribute('aria-pressed'),'true');
    assert.ok(await page.locator('#nar-results-summary').isVisible(),'statistics on results mode');
    await page.locator('[data-reset-scope="nar"]').click();
    assert.equal(await page.locator('#nar-view-number').inputValue(),'all','reset race-number filter');
    assert.equal(await page.locator('#nar-view-date').inputValue(),'today','reset race date');

    await page.locator('.mobile-dock [data-jump="jra"][data-display="results"]').click();
    assert.equal(await page.locator('#jra-view-mode').inputValue(),'results','JRA result mode');
    assert.equal(await page.locator('.mobile-dock [data-jump="jra"][data-display="results"]').getAttribute('aria-current'),'page','JRA result active menu');
    await page.locator('[data-mode-select="jra-view-mode"] [data-mode="predictions"]').click();
    assert.equal(await page.locator('#jra-view-mode').inputValue(),'predictions','JRA prediction mode');
    await page.locator('#jra-view-number').selectOption('11');
    assert.equal(await page.locator('#jra-view-number').inputValue(),'11','JRA race filter');
    await page.locator('[data-reset-scope="jra"]').click();
    assert.equal(await page.locator('#jra-view-number').inputValue(),'all','JRA reset filters');
    assert.deepEqual(errors,[],'no uncaught JavaScript errors');
    console.log('PASS mobile Chromium: home counts, race countdown, refresh, active dock, NAR/JRA filters, reset and prediction/result switches');
  }finally{
    if(browser)await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
}
run().catch(err=>{console.error(err);process.exitCode=1;});

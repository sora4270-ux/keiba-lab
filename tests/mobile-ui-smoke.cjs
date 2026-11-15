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
    let licensedJraFixture={schema_version:1,status:'not_configured',updated_at:null,races:[],drafts:[],schedule:[],summary:{}};
    await page.route('**/data/auto/jra_predictions.json*',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify(licensedJraFixture)}));
    let xWidgetLoads=0;
    await page.route('https://platform.twitter.com/widgets.js',route=>{
      xWidgetLoads++;
      return route.fulfill({contentType:'text/javascript',body:`
        window.twttr={widgets:{createTweet:async (id,target)=>{
          if(id==='456')return undefined;
          const post=document.createElement('div');
          post.textContent='テスト投稿 '+id;
          target.append(post);
          return post;
        }}};
      `});
    });
    await page.goto('http://127.0.0.1:'+server.address().port+'/',{waitUntil:'domcontentloaded'});
    await page.waitForFunction(()=>document.querySelector('#nar-count')?.textContent?.includes('開催情報'),null,{timeout:15000});
    await page.waitForFunction(()=>document.querySelector('#jra-auto-status')?.textContent?.includes('未接続'),null,{timeout:15000});
    assert.ok((await page.locator('#jra-auto-status').innerText()).includes('未接続'),'JRA data remains clearly unconfigured without a license');
    assert.equal(xWidgetLoads,0,'X resources are loaded only when a post is requested');
    assert.equal(await page.locator('.quick-link').count(),4,'home shortcuts');
    assert.ok((await page.locator('#quick-live-summary').innerText()).includes('開催情報 2R'),'summary includes schedule');
    assert.ok((await page.locator('#quick-next-race').innerText()).includes('発走まで約'),'next-race countdown shown');
    assert.ok(await page.locator('#quick-refresh').isVisible(),'manual refresh is available');
    assert.equal(await page.locator('.mobile-dock [data-jump="nar"][data-display="predictions"]').getAttribute('aria-current'),'page','NAR prediction is the initial active menu');
    assert.equal(await page.locator('.mobile-dock button').count(),5,'mobile bottom navigation');
    assert.ok(await page.locator('.mobile-dock').isVisible(),'bottom navigation visible on phone');
    assert.ok((await page.locator('#quick-next-race').innerText()).includes('発走予定'),'next race preview');

    assert.ok((await page.locator('#nar-odds-status').innerText()).includes('取得 0/0R'),'unpublished NAR odds are explicitly reported');
    const narRace={
      id:schedule[0].id,date:today,venue:'園田',race_no:4,name:'架空の試験競走4R',
      start_at:schedule[0].start_at,cutoff_at:new Date(Date.now()+1.75*3600000).toISOString(),
      predicted_at:new Date().toISOString(),status:'draft',model:'form_market_v3_podium',
      top3:[{no:1,name:'架空馬A',win_probability:0.5},{no:2,name:'架空馬B',win_probability:0.3},{no:3,name:'架空馬C',win_probability:0.2}],
      ranking:[{no:1,name:'架空馬A',win_probability:0.5},{no:2,name:'架空馬B',win_probability:0.3},{no:3,name:'架空馬C',win_probability:0.2}],
      market:{horses:[{no:1,odds:2.4,popularity:1},{no:2,odds:4.5,popularity:2},{no:3,odds:7.8,popularity:3}],updated_at:new Date().toISOString()},
      tickets:[[1,2,3]],trio_tickets:[[1,2,3]],result:null
    };
    const source=fs.readFileSync(path.join(root,'index.html'),'utf8');
    const selectTickets=new Function(source.slice(source.indexOf('function predictionTickets('),source.indexOf('const pct='))+';return predictionTickets;')();
    const adaptive=selectTickets([{no:1},{no:2},{no:3}],[.5,.3,.2],[0,1,2]);
    narRace.tickets=adaptive.tickets.map(t=>[t.a+1,t.b+1,t.c+1]);
    // The NAR exporter rounds the saved probability to six decimal places.
    narRace.trifecta_plan={...adaptive.plan,covered_mass:Number(adaptive.plan.covered_mass.toFixed(6))};
    narRace.top5=narRace.top3;
    narRace.trifecta_market_at_lock={updated_at:narRace.predicted_at,odds:{'1-2-3':4}};
    mock.drafts=[narRace];
    await page.locator('#nar-refresh').click();
    await page.waitForFunction(()=>document.querySelector('#nar-odds-status')?.textContent?.includes('取得 1/1R'),null,{timeout:10000});
    const mainBets=page.locator('#nar-races .forecast-bets');
    assert.deepEqual(await mainBets.locator('dt').allTextContents(),['単勝','複勝','馬連','馬単','ワイド']);
    const trio=mainBets.locator('.bet-section').nth(0);
    const trifecta=mainBets.locator('.bet-section').nth(1);
    assert.match(await trio.locator('summary').innerText(),/三連複.*フォーメーション.*1点/);
    assert.match(await trifecta.locator('summary').innerText(),/三連単.*フォーメーション.*6点/);
    await trio.locator('summary').click();
    await trifecta.locator('summary').click();
    assert.deepEqual(await trio.locator('.formation-col small').allTextContents(),['1列目','2列目','3列目']);
    assert.deepEqual(await trifecta.locator('.formation-col small').allTextContents(),['1着','2着','3着']);
    const forecastDetails=page.locator('#nar-races .forecast-details > summary');
    assert.equal(await page.locator('#nar-races .forecast-details').getAttribute('open'),null);
    await forecastDetails.click();
    const allocation=page.locator('#nar-races [data-trifecta-allocation]');
    await allocation.locator('summary').click();
    assert.match(await allocation.locator('[data-allocation-summary]').innerText(),/自動配分は見送り.*0円/);
    await allocation.locator('[data-allocation-mode]').selectOption('manual');
    assert.match(await allocation.locator('[data-allocation-summary]').innerText(),/見送り.*1\/6点/);
    assert.ok(await allocation.getByText('全候補の公式オッズが揃ったレースで配分を計算します。').isVisible());
    const budget=page.locator('#nar-races [data-budget-tickets]');
    await budget.locator('summary').click();
    const yen=budget.locator('[data-budget-amount]');
    const budgetSummary=budget.locator('[data-budget-summary]');
    const budgetPicks=budget.locator('[data-budget-list] .bet-row');
    await yen.fill('250');
    assert.match(await budgetSummary.innerText(),/1点 ／ 合計 100円 ／ 残り 150円/);
    await budget.locator('[data-budget-type]').selectOption('trifecta');
    assert.match(await budgetSummary.innerText(),/2点 ／ 合計 200円 ／ 残り 50円/);
    assert.equal(await budgetPicks.count(),2);
    assert.deepEqual(await budgetPicks.first().locator('.bet-number').allTextContents(),['1着1','2着2','3着3']);
    assert.equal(await budgetPicks.first().locator('.bet-amount').innerText(),'100円');
    await yen.fill('99');
    assert.match(await budgetSummary.innerText(),/0点 ／ 合計 0円 ／ 残り 99円/);
    assert.equal(await budgetPicks.count(),0);
    const narForecastText=await page.locator('#nar-races').innerText();
    assert.ok(narForecastText.includes('単勝2.4倍・1人気'),'NAR odds and popularity shown with top picks');
    assert.ok(narForecastText.includes('単勝4.5倍・2人気'),'second runner also displays verified odds');
    assert.ok(narForecastText.includes('地方競馬公式の単勝オッズ'),'official source labelled');
    assert.ok(narForecastText.includes('三連単 6点・600円'),'adaptive count and actual stake shown');
    assert.ok(narForecastText.includes('候補内網羅度'),'conditional coverage labelled');
    await page.locator('#nar-view-date').selectOption('all');
    assert.ok((await page.locator('#nar-races').innerText()).includes('園田 4R'));
    assert.ok((await page.locator('#nar-races').innerText()).includes('園田 5R'));
    await page.locator('#nar-view-number').selectOption('4');
    assert.ok((await page.locator('#nar-races').innerText()).includes('園田 4R'));
    assert.ok(!(await page.locator('#nar-races').innerText()).includes('園田 5R'),'race-number filter');

    mock.drafts=[];
    const completeQuotes=Object.fromEntries(narRace.tickets.map((ticket,i)=>[ticket.join('-'),i===0?4:20]));
    mock.races=[{...narRace,status:'final',result:[1,2,3],
      trifecta_market_at_lock:{updated_at:narRace.predicted_at,odds:completeQuotes},
      trifecta_diversified_tickets:[...narRace.tickets].reverse(),payouts:{trio:120,trifecta:650}}];
    await page.locator('#nar-refresh').click();
    await page.waitForFunction(()=>document.querySelector('#nar-review')?.textContent?.includes('的中 1R'));
    await page.locator('.quick-link[data-jump="nar"][data-display="results"]').click();
    assert.equal(await page.locator('#nar-view-mode').inputValue(),'results','NAR result mode');
    assert.equal(await page.locator('.mobile-dock [data-jump="nar"][data-display="results"]').getAttribute('aria-current'),'page','active menu follows result tab');
    assert.equal(await page.locator('[data-mode-select="nar-view-mode"] [data-mode="results"]').getAttribute('aria-pressed'),'true');
    assert.ok(await page.locator('#nar-results-summary').isVisible(),'statistics on results mode');
    const review = page.locator('#nar-review');
    assert.ok((await review.innerText()).includes('購入 600円'),'review derives spending from frozen count');
    await review.getByText('1レースの予算別成績（1R）').click();
    assert.ok(await review.getByRole('row').filter({hasText:'500円'}).isVisible(),'budget comparison opens on mobile');
    assert.match(await review.innerText(), /三連単の同点数比較/);
    await review.getByText('三連単の資金配分を比較（1/1R）',{exact:true}).click();
    assert.match(await review.innerText(), /均等配分 \d+\.\d%.*\nオッズに応じた配分 \d+\.\d%/);
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

    const xSearch=page.locator('#jra-x-search');
    const netkeiba=page.locator('#jra-netkeiba');
    const cards=netkeiba.getByRole('link',{name:'出馬表・オッズ ↗'});
    const paybacks=netkeiba.getByRole('link',{name:'結果・払戻 ↗'});
    const netkeibaDate=netkeiba.getByLabel('開催日（任意）');
    assert.equal(await cards.getAttribute('href'),'https://race.netkeiba.com/top/');
    await netkeibaDate.fill('2026-11-15');
    assert.equal(await cards.getAttribute('href'),'https://race.netkeiba.com/top/?kaisai_date=20261115');
    assert.equal(await paybacks.getAttribute('href'),'https://race.netkeiba.com/top/payback_list.html?kaisai_date=20261115');
    await netkeibaDate.fill('');
    assert.equal(await paybacks.getAttribute('href'),'https://race.netkeiba.com/top/payback_list.html');
    await xSearch.evaluate(form=>form.addEventListener('submit',event=>event.preventDefault(),{once:true}));
    await page.locator('#jra-x-race').fill('京都11R');
    await page.locator('#jra-x-date').fill('2026-11-15');
    await xSearch.getByRole('button').click();
    assert.equal(await xSearch.locator('[name="q"]').inputValue(),'京都11R 予想 since:2026-11-14 until:2026-11-16');
    const xPost=page.locator('#jra-x-post');
    const xUrl=page.locator('#jra-x-url');
    const xOriginal=page.locator('#jra-x-original');
    await xUrl.fill('https://x.com.example.com/example/status/123');
    await xPost.getByRole('button').click();
    assert.match(await page.locator('#jra-x-status').innerText(),/URLを入力してください/);
    assert.equal(xWidgetLoads,0,'invalid post URLs do not load the X widget');
    assert.equal(await xOriginal.isVisible(),false);
    await xUrl.fill('https://twitter.com/example/status/123?s=46');
    await xPost.getByRole('button').click();
    await page.locator('#jra-x-preview').getByText('テスト投稿 123').waitFor();
    assert.equal(await xOriginal.getAttribute('href'),'https://x.com/example/status/123');
    await xUrl.fill('https://x.com/i/status/456');
    await xPost.getByRole('button').click();
    await page.locator('#jra-x-status').getByText(/埋め込みを表示できません/).waitFor();
    assert.equal(await xOriginal.getAttribute('href'),'https://x.com/i/status/456');
    assert.equal(xWidgetLoads,1,'the widget is shared across preview requests');
    // Import a future JRA race through the shared CSV intake, then forecast via JRA one-tap controls.
    const future=new Date(Date.now()+48*3600000);
    const nextJst=future.toLocaleDateString('sv-SE',{timeZone:'Asia/Tokyo'});
    const nextTime=future.toLocaleTimeString('en-GB',{timeZone:'Asia/Tokyo',hour:'2-digit',minute:'2-digit',hour12:false});
    const startAt=nextJst+'T'+nextTime+':00+09:00';
    const header='race_id,race_name,date,venue,race_no,start_at,horse_no,horse_name,odds';
    const lines=[['1','青空','3.2'],['2','新風','4.8'],['3','飛躍','6.9'],['4','星空','10.0']]
      .map(([no,name,odds])=>['ui-jra-future','試験競走',nextJst,'東京','11',startAt,no,name,odds].join(','));
    await page.locator('#feed-file').setInputFiles({name:'central-races.csv',mimeType:'text/csv',buffer:Buffer.from([header,...lines].join('\n'))});
    await page.waitForFunction(()=>document.querySelector('#jra-import-count')?.textContent?.includes('取込済み'),null,{timeout:10000});
    assert.ok((await page.locator('#jra-import-count').innerText()).includes('予想可能 1R'),'new JRA import is eligible');
    await page.locator('#jra-predict-imported').click();
    assert.ok((await page.locator('#jra-list').innerText()).includes('東京 11R'),'JRA forecast saved and displayed');
    const raceSearch=new URL(await page.locator('#jra-list .jra-x-link').getAttribute('href'));
    assert.equal(raceSearch.origin,'https://x.com');
    assert.match(raceSearch.searchParams.get('q'),/^東京11R 予想 since:/);
    assert.ok((await page.locator('#jra-list').innerText()).includes('オッズ・人気順'),'JRA odds/popularity detail available');
    await page.emulateMedia({reducedMotion:'reduce'});
    const simulation=page.locator('#race-simulation');
    await page.locator('#jra-list [data-race-simulation]').click();
    assert.equal(await simulation.isVisible(),true);
    assert.equal(await simulation.locator('[data-sim-track] .sim-lane').count(),4);
    assert.equal(await simulation.locator('[data-sim-stats] tr').count(),4);
    await simulation.locator('[data-sim-choice]').selectOption('1');
    await simulation.locator('[data-sim-start]').click();
    await simulation.getByRole('status').filter({hasText:'応援馬'}).waitFor();
    assert.equal(await simulation.locator('[data-sim-finish] li').count(),4);
    await simulation.getByRole('button',{name:'閉じる'}).click();
    assert.equal(await simulation.isVisible(),false);
    assert.ok((await page.locator('#jra-import-count').innerText()).includes('予想可能 0R'),'duplicate prediction disabled');

    // License-enabled backend JSON is rendered without requiring a manual CSV import.
    licensedJraFixture={
      schema_version:1,status:'ready',updated_at:new Date().toISOString(),
      races:[],schedule:[],summary:{},
      drafts:[{
        id:'jra-ui-license-test',date:today,venue:'東京',race_no:11,
        name:'自動配信の表示テスト',start_at:new Date(Date.now()+4*3600000).toISOString(),
        cutoff_at:new Date(Date.now()+3.75*3600000).toISOString(),
        predicted_at:new Date().toISOString(),status:'draft',
        top3:[{no:1,name:'テスト一号',win_probability:0.5,odds:2.1,popularity:1},
              {no:2,name:'テスト二号',win_probability:0.3,odds:4.5,popularity:2},
              {no:3,name:'テスト三号',win_probability:0.2,odds:9.0,popularity:3}],
        trio_tickets:[[1,2,3]],tickets:[[1,2,3]]
      }]
    };
    await page.locator('#jra-view-date').selectOption('all');
    await page.locator('#jra-view-number').selectOption('all');
    await page.locator('#jra-auto-refresh').click();
    await page.waitForFunction(()=>document.querySelector('#jra-auto-status')?.textContent?.includes('接続済み'),null,{timeout:12000});
    assert.ok((await page.locator('#jra-auto-status').innerText()).includes('接続済み'),'licensed feed status');
    assert.ok((await page.locator('#jra-auto-races').innerText()).includes('テスト一号'),'server-side JRA drafts appear without manual input');
    assert.match(await page.locator('#jra-auto-races').innerText(),/三連複.*フォーメーション/);
    await page.locator('.tab[data-tab="predict"]').click();
    await page.locator('#load-sample').click();
    await page.locator('#run-prediction').click();
    assert.equal(await page.locator('#manual-bets dt').count(),5);
    assert.equal(await page.locator('#manual-bets .bet-section').count(),2);
    assert.deepEqual(errors,[],'no uncaught JavaScript errors');
    console.log('PASS mobile Chromium: home counts, race countdown, refresh, active dock, NAR/JRA filters, reset and prediction/result switches');
  }finally{
    if(browser)await browser.close();
    await new Promise(resolve=>server.close(resolve));
  }
}
run().catch(err=>{console.error(err);process.exitCode=1;});

'use strict';
const fs=require('node:fs');
const assert=require('node:assert/strict');
const {execFileSync}=require('node:child_process');
const html=fs.readFileSync('index.html','utf8');
const predictionTickets=new Function(html.slice(html.indexOf('function predictionTickets('),html.indexOf('const pct='))+';return predictionTickets;')();
const fixtures=[
 [.97,.02,.005,.003,.002],
 [.4,.25,.15,.12,.08],
 [.2,.2,.2,.2,.2],
 Array(12).fill(1/12),
 [.7,.2,.1],
 [.4,.3,.2,.1]
];
const python=JSON.parse(execFileSync('python',['-c',`
import sys,json
sys.path.insert(0,'scripts')
from trio_strategy import ticket_ranking,trifecta_plan
out=[]
for ps in json.loads(sys.argv[1]):
    hs=[{'no':i+1} for i in range(len(ps))]
    ids=sorted(range(1,len(ps)+1),key=lambda i:(-ps[i-1],i))
    ordered,_=ticket_ranking(hs,ps,ps,None)
    out.append(trifecta_plan(ids,ordered))
print(json.dumps(out))
`,JSON.stringify(fixtures)],{encoding:'utf8'}));
const counts=[];
fixtures.forEach((ps,i)=>{
 const horses=ps.map((p,i)=>({no:i+1}));
 const rank=ps.map((_,i)=>i).sort((a,b)=>ps[b]-ps[a]||a-b);
 const x=predictionTickets(horses,ps,rank),y=python[i];
 const tickets=x.tickets.map(t=>[horses[t.a].no,horses[t.b].no,horses[t.c].no]);
 assert.deepEqual(tickets,y.tickets,'Python and browser must choose identical tickets');
 assert.ok(tickets.length>=6&&tickets.length<=36);
 assert.equal(x.plan.stake_yen,100*tickets.length);
 assert.ok(Math.abs(x.plan.candidate_mass-y.candidate_mass)<1e-6);
 assert.ok(Math.abs(x.plan.conditional_coverage-y.conditional_coverage)<1e-6);
 assert.equal(new Set(tickets.map(t=>t.join('-'))).size,tickets.length);
 assert.ok(tickets.every(t=>t.length===new Set(t).size&&t.every(n=>rank.slice(0,5).includes(n-1))));
 assert.ok(x.plan.target_reached||tickets.length===36);
 if(tickets.length>6&&x.plan.target_reached){
  assert.ok(x.tickets.slice(0,-1).reduce((a,t)=>a+t.prob,0)<x.plan.candidate_mass*.70);
 }
 counts.push(tickets.length);
});
assert.ok(counts[0]<counts[1]&&counts[1]<counts[2],'concentrated races use fewer tickets');
assert.equal(counts[2],36);
assert.equal(counts[4],6);
const reviewSource=html.slice(html.indexOf('function resultReview('),html.indexOf('function dailyReviewHtml('));
const resultReview=new Function(reviewSource+';return resultReview;')();
const saved={top5:[1,2,3,4,5].map(no=>({no})),tickets:[[1,2,3]]};
assert.equal(resultReview({...saved,result:[1,2,3]}),'的中');
assert.equal(resultReview({...saved,result:[1,3,2]}),'候補内の着順違い');
assert.equal(resultReview({...saved,result:[1,2,6]}),'候補5頭から漏れ');
assert.equal(resultReview({...saved,result:null}),null);
assert.ok(html.includes('<option value="36" selected>全件</option>'),'all 36 picks can be displayed');
console.log('PASS: adaptive count, Python/browser parity, coverage cap, cost and loss classification',counts);

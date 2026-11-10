/**
 * StockLens: PREDECLARED research on transition timing rather than permanent caps.
 * Works ONLY on actual observed adjusted QQQ/TQQQ frozen 2010-2026 prices.
 * Baseline decisions from frozen 8.0; each experiment only alters the timing
 * of a transition. Experiments are interpretations, not video trading rules.
 * Broker/prod writes OFF. No pristine OOS; no Israeli tax modeled.
 */
import {readFileSync} from 'node:fs';
const src=JSON.parse(readFileSync('research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json','utf8'));
const bars=src.daily,N=bars.length,START=200,CAP=100000,INV=.985,FEE=.0002,dates=bars.map(r=>r.date),c=bars.map(r=>r.qc);
if(N!==4191||src.snapshot_sha256!=='bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129')throw Error('SOURCE_CHANGED');
for(let i=0;i<N;i++){const r=bars[i];if(i&&r.date<=dates[i-1])throw Error('BAD_ORDER');if(!(r.signal<r.date)||![0,1.25,2,3].includes(r.l))throw Error('BAD_FROZEN_SIGNAL');for(const k of ['qo','qc','to','tc'])if(!(r[k]>0&&Number.isFinite(r[k])))throw Error('BAD_PRICE');}
function ema(x,p){let z=x[0],a=2/(p+1);return x.map(v=>z=v*a+z*(1-a));}
const e20=ema(c,20),fast=ema(c,6),slow=ema(c,13),macd=fast.map((v,i)=>v-slow[i]),sig=ema(macd,5);
const sma=Array(N).fill(null);let rolling=c.slice(0,200).reduce((a,b)=>a+b,0);
for(let i=199;i<N;i++){sma[i]=rolling/200;if(i+1<N)rolling+=c[i+1]-c[i-199];}
const rsi=Array(N).fill(50);let up=0,down=0;
for(let i=1;i<N;i++){const dx=c[i]-c[i-1];up=(up*6+Math.max(0,dx))/7;down=(down*6+Math.max(0,-dx))/7;rsi[i]=down?100-100/(1+up/down):100;}
const families=['upshift_confirmation','early_rebound','shock_pulse'];
/** Pre-registered deterministic layer behavior. */
function build(names){
 const lv=Array(N).fill(0),counts={deferred_upshift_days:0,advanced_upshift_days:0,shock_reduction_days:0};
 let last=0,pending=0,boostStart=-100,boostEnd=-1,shockStart=-100,shockEnd=-1;
 for(let i=START;i<N;i++){
  const b=bars[i].l,j=i-1,hist=macd[j]-sig[j],strong=c[j]>e20[j]&&hist>0;
  let tgt=b;
  if(names.includes('upshift_confirmation')){
   if(b>last){
    if(strong){tgt=b;pending=0;}
    else if(pending<2){tgt=last;pending++;counts.deferred_upshift_days++;}
    else{tgt=b;pending=0;}
   }else pending=0;
  }
  if(names.includes('early_rebound')){
   const plateau=i>=START+3 && bars[i-1].l===b&&bars[i-2].l===b&&bars[i-3].l===b;
   const recovery=b>0&&b<=2&&c[j]>sma[j]*1.01&&strong&&rsi[j]>=55&&c[j]>c[j-5];
   if(recovery&&plateau&&i>boostStart+8){boostStart=i;boostEnd=i+2;}
   if(recovery&&i<=boostEnd){
    tgt=Math.max(tgt,b===1.25?2:3);
    if(tgt>b)counts.advanced_upshift_days++;
   }
  }
  if(names.includes('shock_pulse')){
   const shock=c[j]/c[j-1]-1<=-.025&&c[j]<e20[j];
   if(shock&&b>1.25&&i>shockStart+10){shockStart=i;shockEnd=i+1;}
   if(b>0&&i<=shockEnd){
    const cap=b>=3?2:1.25;
    if(tgt>cap){tgt=cap;counts.shock_reduction_days++;}
   }
  }
  if(b===0)tgt=0;
  if(![0,1.25,2,3].includes(tgt))throw Error('INVALID_TARGET');
  lv[i]=tgt;last=tgt;
 }
 return {lv,counts,changed_sessions:lv.slice(START).filter((v,k)=>v!==bars[START+k].l).length};
}
function execute(levels,extraLag=0,slipBps=10){
 if(![0,1].includes(extraLag)||![10,20].includes(slipBps))throw Error('BAD_STRESS');
 const slip=slipBps/10000;let cash=CAP,q=0,t=0,transactions=0,turnover=0,feeCost=0,slipCost=0,prev=null;const navs=[];
 function trade(symbol,quantity,price,buy){
  let qty=Math.floor(Math.max(0,quantity));const held=symbol==='q'?q:t;
  qty=buy?Math.min(qty,Math.floor(Math.max(0,cash)/(price*(1+slip)*(1+FEE)))):Math.min(qty,held);
  if(!qty)return;
  const value=qty*price;
  cash+=buy?-value*(1+slip)*(1+FEE):value*(1-slip)*(1-FEE);
  if(symbol==='q')q+=buy?qty:-qty;else t+=buy?qty:-qty;
  transactions++;turnover+=value;feeCost+=value*FEE;slipCost+=value*slip;
 }
 for(let i=START;i<N;i++){
  const r=bars[i],lev=i-extraLag>=START?levels[i-extraLag]:0;
  if(prev===null||lev!==prev){
   const eq=cash+q*r.qo+t*r.to;
   const tw=lev>0?(lev-1)/2:0,qw=lev>0?1-tw:0;
   const qneed=Math.floor(eq*INV*qw/r.qo),tneed=Math.floor(eq*INV*tw/r.to);
   trade('q',q-qneed,r.qo,false);trade('t',t-tneed,r.to,false);
   trade('q',qneed-q,r.qo,true);trade('t',tneed-t,r.to,true);
  }
  const nav=cash+q*r.qc+t*r.tc;
  if(!Number.isFinite(nav)||nav<=0||cash<-.000001)throw Error('INVALID_ACCOUNT');
  navs.push(nav);prev=lev;
 }
 return {navs,transactions,turnover,feeCost,slipCost};
}
function metrics(p,start=0,end=p.navs.length-1){
 const seed=start?p.navs[start-1]:CAP,values=p.navs;
 let peak=seed,dd=0;
 for(let i=start;i<=end;i++){peak=Math.max(peak,values[i]);dd=Math.min(dd,values[i]/peak-1);}
 const begin=dates[START+start],finish=dates[START+end],years=(Date.parse(finish)-Date.parse(begin))/86400000/365.2425;
 return {cagr:(values[end]/seed)**(1/years)-1,maxdd:dd,return:values[end]/seed-1,terminal_equity:values[end]};
}
const eras={early:['2010-11-26','2016-12-30'],middle:['2017-01-03','2021-12-31'],recent:['2022-01-03','2026-10-09'],y2022:['2022-01-03','2022-12-30'],y2024:['2024-01-02','2024-12-31']};
function era(p,bound){
 const [from,to]=bound;let first=-1,last=-1;
 for(let i=START;i<N;i++)if(dates[i]>=from&&dates[i]<=to){if(first<0)first=i-START;last=i-START;}
 if(first<0)throw Error('MISSING_ERA');
 return metrics(p,first,last);
}
const tests=Array.from({length:8},(_,mask)=>{const names=families.filter((_,k)=>mask&(1<<k));return {name:names.join('+')||'FROZEN_8',names,mask,...build(names)};});
for(const x of tests)for(let i=START;i<N;i++)if(bars[i].l===0&&x.lv[i]!==0)throw Error('DEFENSE_BREACH');
const base=execute(tests[0].lv),b=metrics(base);
if(base.transactions!==127||Math.abs(b.cagr-.39835414489537446)>1e-9||Math.abs(b.maxdd+.4907616145480055)>1e-9)throw Error('COHORT_PARITY_FAIL');
const refStress={};for(const lag of [0,1])for(const slip of [10,20])refStress[lag+'_'+slip]=metrics(execute(tests[0].lv,lag,slip));
const results=tests.map(x=>{
 const p=execute(x.lv),m=metrics(p),stress=[];
 for(const lag of [0,1])for(const slip of [10,20]){
  const v=metrics(execute(x.lv,lag,slip)),z=refStress[lag+'_'+slip];
  stress.push({additional_decision_lag:lag,slippage_bps_per_side:slip,cagr_delta_pp:100*(v.cagr-z.cagr),maxdd_gain_pp:100*(v.maxdd-z.maxdd)});
 }
 return {name:x.name,names:x.names,component_count:x.names.length,changed_sessions:x.changed_sessions,counters:x.counts,...m,
  cagr_delta_pp:100*(m.cagr-b.cagr),maxdd_gain_pp:100*(m.maxdd-b.maxdd),
  trades:p.transactions,turnover:p.turnover,fees:p.feeCost,slippage:p.slipCost,
  by_era:Object.fromEntries(Object.entries(eras).map(([k,v])=>[k,era(p,v)])),stress};
});
console.log(JSON.stringify({schema_version:1,kind:'FROZEN8_TRANSITION_TIMING_SCREEN',
 source_snapshot_sha256:src.snapshot_sha256,window:{start:dates[START],end:dates.at(-1),sessions:N-START},
 all_outputs_reused_in_sample:true,frozen8_parity:true,initial_capital_usd:CAP,
 implementation:'observed adjusted QQQ/TQQQ, prior completed close signal/next OPEN, 2bps fees+10bps slippage per side, whole shares, no cash yield',
 thresholds:'predeclared research interpretations: confirmation max 2 sessions; rebound RSI7>=55, SMA200+1%, EMA20 and MACD(6,13,5) positive, 3-day frozen plateau, 3-day pulse, 8-day cooldown; shock daily QQQ -2.5% below EMA20, 2-day downshift, 10-day cooldown',
 combinations:results,real_breadth_tested:false,full_autopilot_tested:false,israeli_tax_modeled:false,
 pristine_heldout_test:false,broker_orders:false,production_changed:false,automatic_promotion:false
},null,2));
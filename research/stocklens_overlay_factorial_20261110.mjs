/**
 * SL-58 / SL-59 / SL-60 — 2^4 layered risk-overlay factorial research.
 *
 * Replays FROZEN StockLens 8.0 target levels, then overlays independent
 * risk caps. Does not mutate the frozen model, production, AWS or brokers.
 *
 * Evidence: actual adjusted QQQ/TQQQ daily OPEN/CLOSE from frozen snapshot.
 * All trade indications are derived only from the PRIOR completed close.
 * NOT a recreation of the full Autopilot system, nor real market breadth.
 * Run: node research/stocklens_overlay_factorial_20261110.mjs
 */
import {readFileSync} from 'node:fs';
const PATH='research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json';
const source=JSON.parse(readFileSync(PATH,'utf8'));
const bars=source.daily;
const N=bars.length, WARM=200, START=100000, INVESTED=.985, FEE_BPS=2;
if(N!==4191 || source.period.start!=='2010-02-11'||source.period.end!=='2026-10-09'
   ||source.snapshot_sha256!=='bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129')
   throw Error('SOURCE_SNAPSHOT_MISMATCH');
const dates=bars.map(b=>b.date),q=bars.map(b=>b.qc),t=bars.map(b=>b.tc);
for(let i=0;i<N;i++){
 const r=bars[i];
 if(i&&r.date<=bars[i-1].date)throw Error('UNSORTED_DATES');
 if(!(r.signal<r.date) || ![0,1.25,2,3].includes(r.l))throw Error('INVALID_FROZEN_LEVEL_OR_SIGNAL');
 for(const field of ['qo','qc','to','tc'])if(!Number.isFinite(r[field])||r[field]<=0)throw Error('INVALID_OBSERVED_PRICE');
}
function ema(values,period){
 const a=2/(period+1);let previous=values[0];return values.map(v=>previous=a*v+(1-a)*previous);
}
const sma200=Array(N).fill(null);
for(let i=199,rolling=q.slice(0,200).reduce((a,b)=>a+b,0);i<N;i++){
 sma200[i]=rolling/200;
 if(i+1<N)rolling+=q[i+1]-q[i-199];
}
const gains=Array(N).fill(0),rsi=Array(N).fill(50);
let avgGain=0,avgLoss=0;
for(let i=1;i<N;i++){
 const delta=q[i]-q[i-1];avgGain=(avgGain*6+Math.max(0,delta))/7;avgLoss=(avgLoss*6+Math.max(0,-delta))/7;
 rsi[i]=avgLoss===0?100:100-100/(1+avgGain/avgLoss);
}
// Masonson mentions fast MACD 6/13/5 but not a trading-rule specification.
// We choose a risk cap (NOT a claimed replication of his own trades).
const ema6=ema(q,6),ema13=ema(q,13);
const macd=ema6.map((v,i)=>v-ema13[i]),macdSignal=ema(macd,5);
const ema8=ema(t,8);
const deltas=t.map((v,i)=>i?v-t[i-1]:0);
const tsiN=ema(ema(deltas,25),13),tsiD=ema(ema(deltas.map(Math.abs),25),13);
const tsi=tsiN.map((v,i)=>tsiD[i]?100*v/tsiD[i]:0);
const tsiSignal=ema(tsi,7);
// Risk overlays, each independently computed from PRIOR completed session.
// A: 1% SMA200 hysteretic cash gate on QQQ, applied on top of stocklens8.
// B: RSI7(QQQ)<25 => cap target exposure at 1.25x.
// C: MACD(6,13,5)(QQQ) below signal => cap target at 2x.
// D: TQQQ under EMA8 OR TSI(25,13,7) below its signal => cap at 1.25x.
// B/C/D cap thresholds & trade actions are researcher-defined counterfactuals.
const KEYS=['LRS','RSI','MACD','TSI_EMA'];
const caps=Object.fromEntries(KEYS.map(x=>[x,Array(N).fill(3)]));
let trendOn=false;
for(let i=WARM;i<N;i++){
 const previous=i-1;
 const s=sma200[previous],close=q[previous];
 trendOn=trendOn ? close>=s*.99 : close>s*1.01;
 caps.LRS[i]=trendOn?3:0;
 caps.RSI[i]=rsi[previous]<25?1.25:3;
 caps.MACD[i]=macd[previous]<macdSignal[previous]?2:3;
 caps.TSI_EMA[i]=(t[previous]>ema8[previous] && tsi[previous]>tsiSignal[previous])?3:1.25;
}
const choices=[...Array(16).keys()].map(mask=>{
 const names=KEYS.filter((_,idx)=>mask & (1<<idx));
 const targets=bars.map((r,i)=>i<WARM?0:Math.min(r.l,...names.map(k=>caps[k][i])));
 const changed=targets.slice(WARM).filter((v,i)=>v!==bars[WARM+i].l).length;
 return {name:names.length?names.join('+'):'FROZEN_8',mask,layer_count:names.length,layers:names,targets,changed_sessions:changed};
});
function simulate(targets,{extraLag=0,slippageBps=10}={}){
 if(![0,1].includes(extraLag)||![10,20].includes(slippageBps))throw Error('BAD_STRESS_PARAMETER');
 const slip=slippageBps/10000,fee=FEE_BPS/10000;
 let cash=START,qs=0,ts=0,trades=0,turnover=0,commission=0,slippage=0,prior=null;
 const navs=[];
 function transact(side,symbol,quantity,price){
  let available=symbol==='q'?qs:ts;
  let amount=Math.max(0,Math.floor(side==='sell'?Math.min(quantity,available):quantity));
  if(side==='buy')amount=Math.min(amount,Math.floor(Math.max(0,cash)/(price*(1+slip)*(1+fee))));
  if(!amount)return;
  const notional=amount*price;
  if(side==='sell'){
   cash+=notional*(1-slip)*(1-fee);
   if(symbol==='q')qs-=amount;else ts-=amount;
  }else{
   cash-=notional*(1+slip)*(1+fee);
   if(symbol==='q')qs+=amount;else ts+=amount;
  }
  trades++;turnover+=notional;commission+=notional*fee;slippage+=notional*slip;
 }
 for(let i=WARM;i<N;i++){
  const level=i-extraLag>=WARM?targets[i-extraLag]:0;
  const r=bars[i];
  if(prior===null||level!==prior){
   const equity=cash+qs*r.qo+ts*r.to;
   const tw=level===0?0:(level-1)/2,qw=level===0?0:1-tw;
   const newQ=Math.floor(equity*qw*INV/r.qo);
   const newT=Math.floor(equity*tw*INV/r.to);
   transact('sell','q',qs-newQ,r.qo);transact('sell','t',ts-newT,r.to);
   transact('buy','q',newQ-qs,r.qo);transact('buy','t',newT-ts,r.to);
  }
  const nav=cash+qs*r.qc+ts*r.tc;
  if(!Number.isFinite(nav)||nav<=0||cash<-.00001||qs<0||ts<0)throw Error('LEDGER_INVALID:'+i);
  navs.push(nav);prior=level;
 }
 return {navs,trades,turnover,commission,slippage};
}
function wholeBaselineParity(){
 let cash=START,qs=0,ts=0,trades=0,prior=null;
 for(let i=0;i<N;i++){
  const r=bars[i],lev=r.l;
  if(prior===null||prior!==lev){
   const equity=cash+qs*r.qo+ts*r.to,tw=lev===0?0:(lev-1)/2,qw=lev===0?0:1-tw;
   const newQ=Math.floor(equity*qw*INV/r.qo),newT=Math.floor(equity*tw*INV/r.to);
   for(const [sym,amt,px]of [['q',qs-newQ,r.qo],['t',ts-newT,r.to]]){
    if(amt<=0)continue;
    cash+=amt*px*(1-.001)*(1-.0002);if(sym==='q')qs-=amt;else ts-=amt;trades++;
   }
   for(const [sym,amt,px]of [['q',newQ-qs,r.qo],['t',newT-ts,r.to]]){
    if(amt<=0)continue;
    const unit=px*(1+.001)*(1+.0002),qty=Math.min(amt,Math.floor(Math.max(0,cash)/unit));
    if(qty<=0)continue;
    cash-=qty*unit;if(sym==='q')qs+=qty;else ts+=qty;trades++;
   }
  }
  prior=lev;
 }
 const equity=cash+qs*bars.at(-1).qc+ts*bars.at(-1).tc;
 if(trades!==source.without_contributions.strategy.trades||Math.abs(equity-source.without_contributions.strategy.ending_equity)>.01)throw Error('FROZEN_BASELINE_PARITY_FAILED');
 return {passed:true,trades,terminal_equity:equity};
}
function metrics(run){
 let peak=START,dd=0,old=START,total=0,squares=0;
 for(const v of run.navs){peak=Math.max(peak,v);dd=Math.min(dd,v/peak-1);const ret=v/old-1;total+=ret;squares+=ret*ret;old=v;}
 const count=run.navs.length,variance=(squares-total*total/count)/(count-1);
 const yrs=(Date.parse(dates.at(-1))-Date.parse(dates[WARM]))/(86400000*365.2425);
 const cagr=(run.navs.at(-1)/START)**(1/yrs)-1;
 return {cagr,maxdd:dd,volatility:Math.sqrt(Math.max(0,variance)*252),terminal_equity:run.navs.at(-1),trades:run.trades,turnover:run.turnover,fees:run.commission,slippage:run.slippage};
}
function era(run,start,end){
 const idx=[];for(let k=WARM;k<N;k++)if(dates[k]>=start&&dates[k]<=end)idx.push(k-WARM);
 const a=idx[0],b=idx.at(-1);if(a===undefined)throw Error('MISSING_ERA');
 const initial=a>0?run.navs[a-1]:START,last=run.navs[b];
 const years=(Date.parse(dates[WARM+b])-Date.parse(dates[WARM+a]))/(86400000*365.2425);
 let peak=initial,dd=0;
 for(let i=a;i<=b;i++){peak=Math.max(peak,run.navs[i]);dd=Math.min(dd,run.navs[i]/peak-1);}
 return {cagr:(last/initial)**(1/years)-1,maxdd:dd,return:last/initial-1};
}
const frozenParity=wholeBaselineParity();
const paths=choices.map(c=>({choice:c,run:simulate(c.targets)}));
const base=metrics(paths[0].run);
if(Math.abs(base.cagr-.39835414489537446)>1e-9||Math.abs(base.maxdd-(-.4907616145480055))>1e-8)throw Error('WARM_BASELINE_PARITY_FAILED');
const eras={early:['2010-11-26','2016-12-31'],middle:['2017-01-01','2021-12-31'],recent:['2022-01-01','2026-10-09']};
const comparisons=paths.map(({choice:c,run})=>{
 const m=metrics(run);
 const stress=[];
 for(const extraLag of [0,1])for(const slippageBps of [10,20]){
  const x=metrics(simulate(c.targets,{extraLag,slippageBps}));
  const y=metrics(simulate(choices[0].targets,{extraLag,slippageBps}));
  stress.push({extra_lag:extraLag,slippage_bps:slippageBps,
    cagr_delta_pp:100*(x.cagr-y.cagr),maxdd_improvement_pp:100*(x.maxdd-y.maxdd),
    turnover_ratio:y.turnover?x.turnover/y.turnover:undefined});
 }
 return {name:c.name,layers:c.layers,layer_count:c.layer_count,
  changed_sessions:c.changed_sessions,...m,
  cagr_delta_pp:100*(m.cagr-base.cagr),maxdd_improvement_pp:100*(m.maxdd-base.maxdd),
  after_tax:false,
  eras:Object.fromEntries(Object.entries(eras).map(([k,[a,b]])=>[k,era(run,a,b)])),
  stress};
});
const response={
 schema_version:1,
 kind:'STOCKLENS_FROZEN_8_RISK_OVERLAY_FACTORIAL_2POW4',
 asof:dates.at(-1),window:{start:dates[WARM],end:dates.at(-1),sessions:N-WARM},
 source_snapshot_sha256:source.snapshot_sha256,full_baseline_parity:frozenParity,
 overlays:{LRS:'QQQ SMA200 +/-1% hysteretic cash gate',RSI:'QQQ RSI7 <25 cap at 1.25x',MACD:'QQQ MACD(6,13,5) below signal cap at 2x',
  TSI_EMA:'TQQQ close below EMA8 or TSI(25,13,7) below signal cap at 1.25x'},
 approach:'all overlays use min(frozen StockLens 8 exposure, applicable overlay caps); all indicators use previous completed close only',
 execution:'whole share; signal prior close -> next OPEN; adjusted observed QQQ/TQQQ daily prices; 2bps commission+10bps slippage per side; zero cash interest',
 count:comparisons.length,
 comparisons,
 limitation_flags:{market_breadth:'NOT_TESTED_NO_POINT_IN_TIME_CONSTITUENTS',
  full_autopilot:'NOT_TESTED_INCOMPLETE_RULES_AND_INTRADAY_FILLS',
  original_masonson:'NOT_REPLICATED_ONLY_RISK_CAP_PROXY',
  true_nasdaq100_index:'QQQ_PROXY_ONLY',israeli_tax:'NOT_MODELED',pristine_out_of_sample:false,
  broker_orders:false,automatic_promotion:false,prod_modified:false}
};
console.log(JSON.stringify(response,null,2));

/**
 * StockLens exploratory comparison - observed QQQ/TQQQ (2010-2026).
 * Read-only, broker disabled, production untouched.
 * Run from repo root: node research/backtest_challenger_batch_20261110.mjs
 * Outputs JSON on stdout. Requires node >=20, no external dependencies.
 */
import { readFileSync } from 'node:fs';
const sourceFile='research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json';
const raw=JSON.parse(readFileSync(sourceFile,'utf8'));
const daily=raw.daily;
const FEE=.0002,SLIP=.001,INV=.985,CAP=100000,WARM=200;
if(daily.length!==4191||raw.period.start!=='2010-02-11'||raw.period.end!=='2026-10-09')throw Error('FROZEN_SOURCE_CHANGED');
for(let i=0;i<daily.length;i++){
 const r=daily[i];
 if(i&&r.date<=daily[i-1].date)throw Error('INVALID_ORDER');
 if(![0,1.25,2,3].includes(r.l)||!(r.signal<r.date))throw Error('INVALID_SIGNAL');
 for(const k of ['qo','qc','to','tc'])if(!Number.isFinite(r[k])||r[k]<=0)throw Error('INVALID_PRICE');
}
const n=daily.length,dates=daily.map(r=>r.date),qc=daily.map(r=>r.qc),tc=daily.map(r=>r.tc);
function ema(arr,p){const a=2/(p+1);let v=arr[0];return arr.map(x=>(v=x*a+v*(1-a)));}
const ema8=ema(tc,8);
const changes=tc.map((v,i)=>i?v-tc[i-1]:0);
const tsiNum=ema(ema(changes,25),13),tsiDen=ema(ema(changes.map(Math.abs),25),13);
const tsi=tsiNum.map((v,i)=>tsiDen[i]?100*v/tsiDen[i]:0),tsiSignal=ema(tsi,7);
const sma200=[],rsi7=[];let gain=0,loss=0;
for(let i=0;i<n;i++){
 sma200.push(i>=199?qc.slice(i-199,i+1).reduce((a,b)=>a+b,0)/200:null);
 if(!i){rsi7.push(50);continue;}
 const diff=qc[i]-qc[i-1];
 gain=(gain*6+Math.max(0,diff))/7;
 loss=(loss*6+Math.max(0,-diff))/7;
 rsi7.push(loss?100-100/(1+gain/loss):100);
}
function portfolio(){return {cash:CAP,q:0,t:0,trades:0,fees:0,slippage:0,turnover:0,entry:0,partialA:false,partialB:false};}
function nav(p,r,at){return p.cash+p.q*r[at==='open'?'qo':'qc']+p.t*r[at==='open'?'to':'tc'];}
function sell(p,key,quantity,open){
 const qty=Math.max(0,Math.min(quantity,p[key]));if(!qty)return;
 const gross=qty*open;
 p.cash+=gross*(1-SLIP)*(1-FEE);p[key]-=qty;
 p.trades++;p.fees+=gross*FEE;p.slippage+=gross*SLIP;p.turnover+=gross;
}
function buy(p,key,quantity,open){
 const unit=open*(1+SLIP)*(1+FEE),qty=Math.max(0,Math.min(quantity,Math.floor(Math.max(0,p.cash)/unit)));
 if(!qty)return;
 const gross=qty*open;
 p.cash-=qty*unit;p[key]+=qty;
 p.trades++;p.fees+=gross*FEE;p.slippage+=gross*SLIP;p.turnover+=gross;
}
function rebalance(p,r,lev){
 const t=lev<=0?0:(lev-1)/2,q=lev<=0?0:1-t;
 const equity=nav(p,r,'open'),targetQ=Math.floor(equity*q*INV/r.qo),targetT=Math.floor(equity*t*INV/r.to);
 sell(p,'q',p.q-targetQ,r.qo);sell(p,'t',p.t-targetT,r.to);
 buy(p,'q',targetQ-p.q,r.qo);buy(p,'t',targetT-p.t,r.to);
}
function simulate(levels,start=WARM){
 const p=portfolio(),navs=[];let prev=null;
 for(let i=start;i<n;i++){
  const target=levels[i];
  if(prev===null||prev!==target)rebalance(p,daily[i],target);
  const v=nav(p,daily[i],'close');
  if(!Number.isFinite(v)||v<=0||p.cash<-.00001)throw Error('BAD_LEDGER');
  navs.push(v);prev=target;
 }
 return {navs,trades:p.trades,turnover:p.turnover,fees:p.fees,slippage:p.slippage};
}
const lrs=dates.map(()=>0),band=dates.map(()=>0);
for(let i=WARM;i<n;i++){
 const x=qc[i-1],s=sma200[i-1];
 lrs[i]=x>s?3:0;
 band[i]=i===WARM?(x>s*1.01?3:0):(band[i-1]===3?(x<s*.99?0:3):(x>s*1.01?3:0));
}
const frozen=daily.map(r=>r.l);
const rsiCap=dates.map((_,i)=>i<WARM?0:Math.min(frozen[i],rsi7[i-1]<25?1.25:3));
function simulateAuto(strict){
 const p=portfolio(),navs=[],holds=[];let entries=0,entered=-1;
 for(let i=WARM;i<n;i++){
  const r=daily[i],y=i-1;
  const aboveQQQ=qc[y]>sma200[y],crossEMA=tc[y]>ema8[y]&&tc[y-1]<=ema8[y-1],tsiup=tsi[y]>tsiSignal[y];
  const entry=aboveQQQ&&crossEMA&&tsiup&&(!strict||tsi[y]>0);
  if(p.t===0&&entry){
   const qty=Math.floor(p.cash*INV/(r.to*(1+SLIP)*(1+FEE)));
   buy(p,'t',qty,r.to);
   if(p.t){entered=i;p.entry=r.to*(1+SLIP)*(1+FEE);p.partialA=false;p.partialB=false;entries++;}
  }else if(p.t>0){
   const exit=tc[y]<=p.entry*.95||tc[y]<ema8[y]||(strict&&tsi[y]<tsiSignal[y]);
   if(exit){
    sell(p,'t',p.t,r.to);holds.push(i-entered);p.entry=0;
   }else{
    if(!p.partialA&&tc[y]>=p.entry*1.1){sell(p,'t',Math.max(1,Math.floor(p.t/3)),r.to);p.partialA=true;}
    if(!p.partialB&&tc[y]>=p.entry*1.2){sell(p,'t',Math.max(1,Math.floor(p.t/2)),r.to);p.partialB=true;}
   }
  }
  const v=nav(p,r,'close');if(!Number.isFinite(v)||v<=0)throw Error('BAD_AUTO');
  navs.push(v);
 }
 return {navs,trades:p.trades,turnover:p.turnover,fees:p.fees,slippage:p.slippage,entries,avgHoldSessions:holds.length?holds.reduce((a,b)=>a+b,0)/holds.length:null};
}
function metrics(p,start=WARM){
 const vals=p.navs,days=dates.slice(start);
 let peak=CAP,old=CAP,dd=0,ret=[];
 for(const v of vals){peak=Math.max(peak,v);dd=Math.min(dd,v/peak-1);ret.push(v/old-1);old=v;}
 const years=(Date.parse(days.at(-1))-Date.parse(days[0]))/86400000/365.2425;
 const avg=ret.reduce((a,b)=>a+b,0)/ret.length;
 const volatility=Math.sqrt(ret.reduce((a,b)=>a+(b-avg)**2,0)/(ret.length-1)*252);
 return {cagr:(vals.at(-1)/CAP)**(1/years)-1,maxdd:dd,volatility,ending_equity:vals.at(-1),trades:p.trades,turnover:p.turnover,fees:p.fees,slippage:p.slippage,...(p.entries===undefined?{}:{entries:p.entries,avgHoldSessions:p.avgHoldSessions})};
}
function year(p,yr){
 const days=dates.slice(WARM),ind=[];
 for(let i=0;i<days.length;i++)if(days[i].startsWith(String(yr)))ind.push(i);
 const a=ind[0],b=ind.at(-1);if(a===undefined)return null;
 const start=a?p.navs[a-1]:CAP;let peak=start,dd=0;
 for(let i=a;i<=b;i++){peak=Math.max(peak,p.navs[i]);dd=Math.min(dd,p.navs[i]/peak-1);}
 return {return:p.navs[b]/start-1,maxdd:dd};
}
const observed={
 qqq_buy_hold:simulate(dates.map(()=>1)),
 tqqq_buy_hold:simulate(dates.map(()=>3)),
 stocklens8_frozen:simulate(frozen),
 lrs200:simulate(lrs),
 lrs200_hysteresis1pct:simulate(band),
 rsi7_cap_exploratory:simulate(rsiCap),
 autopilot_ema8_tsi_proxy:simulateAuto(false),
 autopilot_ema8_tsi_strict_proxy:simulateAuto(true)
};
const fullBaseline=simulate(frozen,0);
const parity=Math.abs(fullBaseline.navs.at(-1)-raw.without_contributions.strategy.ending_equity)<.01&&fullBaseline.trades===raw.without_contributions.strategy.trades;
if(!parity)throw Error('FROZEN_BASELINE_NOT_REPRODUCED');
const result={
 schema_version:1,kind:'STOCKLENS_LRS_AUTOPILOT_BREADTH_EXPLORATORY',
 source_file:sourceFile,source_snapshot_sha256:raw.snapshot_sha256,
 source_period:raw.period,window:{start:dates[WARM],end:dates.at(-1),sessions:n-WARM},
 observed_real_tqqq:true,synthetic_prices_used:false,
 model:'pre-tax observed adjusted OHLC, daily next-open proxy, whole shares, 2bps fees + 10bps slippage per side, cash earns zero',
 frozen_full_period_parity:{passed:parity,nav:fullBaseline.navs.at(-1),trades:fullBaseline.trades},
 metrics:Object.fromEntries(Object.entries(observed).map(([k,v])=>[k,metrics(v)])),
 years:Object.fromEntries(Object.entries(observed).map(([k,v])=>[k,{2022:year(v,2022),2024:year(v,2024)}])),
 breadth_status:'BLOCKED_POINT_IN_TIME_CONSTITUENTS_UNAVAILABLE',
 autopilot_status:'UNVERIFIED_DAILY_CLOSE_PROXY_RULES_INCOMPLETE',
 israeli_tax_status:'NOT_MODELED_NO_HISTORICAL_NIS_FX_LOTS',
 pristine_oos:false,broker_orders:false,automatic_promotion:false,prod_modified:false
};
console.log(JSON.stringify(result,null,2));
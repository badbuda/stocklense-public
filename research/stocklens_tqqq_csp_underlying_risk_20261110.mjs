/**
 * StockLens TQQQ put-option risk probe. This is NOT an options backtest:
 * no historical contract quote premiums, rolls, early assignments, hedges or tax.
 * It measures observed underlying TQQQ downside over 21 trading sessions
 * conditional on frozen 8.0 level (especially "cash"=0).
 *
 * No broker, live/prod, or model changes.
 */
import {readFileSync} from 'node:fs';
const PATH='research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json';
const src=JSON.parse(readFileSync(PATH,'utf8'));
const bars=src.daily,N=bars.length,START=200,H=21;
const SNAP='bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129';
if(src.snapshot_sha256!==SNAP||N!==4191||src.period.end!=='2026-10-09')throw Error('SOURCE_CHANGED');
for(let i=0;i<N;i++){const r=bars[i];if(i&&r.date<=bars[i-1].date)throw Error('ORDER');if(!(r.signal<r.date)||![0,1.25,2,3].includes(r.l))throw Error('SIGNAL');for(const k of ['qo','qc','to','tc'])if(!Number.isFinite(r[k])||r[k]<=0)throw Error('PRICE');}
function pct(x){return Number(x.toFixed(4));}
function quantile(arr,p){if(!arr.length)return null;const a=[...arr].sort((x,y)=>x-y);const z=(a.length-1)*p,i=Math.floor(z),j=Math.ceil(z);return a[i]+(a[j]-a[i])*(z-i);}
const events=[];
for(let i=START;i+H<N;i++){
 const r=bars[i],future=bars[i+H];
 const futureCloses=bars.slice(i+1,i+H+1).map(x=>x.tc);
 events.push({date:r.date,state:r.l,entryOpen:r.to,expiryClose:future.tc,
   lowestFutureClose:Math.min(...futureCloses),futureReturn:future.tc/r.to-1,
   disjointGrid:(i-START)%H===0});
}
const filters={
 all:e=>true,
 cash:e=>e.state===0,
 risk_on:e=>e.state>0,
 three_x:e=>e.state===3,
 moderate:e=>e.state===1.25||e.state===2,
 y2022:e=>e.date.startsWith('2022'),
 y2024:e=>e.date.startsWith('2024'),
 cash2022:e=>e.date.startsWith('2022')&&e.state===0
};
function sample(arr,discount){
 if(!arr.length)return {n:0};
 const tmp=arr.map(e=>{const strike=e.entryOpen*(1-discount);return {
   itm:Number(e.expiryClose<strike),breached:Number(e.lowestFutureClose<strike),
   collateralLoss:Math.max(0,(strike-e.expiryClose)/strike)};});
 const erosion=tmp.map(x=>x.collateralLoss);
 return {n:arr.length,expiryITMpct:pct(100*tmp.reduce((a,x)=>a+x.itm,0)/arr.length),
   atLeastOneCloseBreachPct:pct(100*tmp.reduce((a,x)=>a+x.breached,0)/arr.length),
   meanCollateralLossExPremiumPct:pct(100*erosion.reduce((a,b)=>a+b,0)/arr.length),
   p95CollateralLossExPremiumPct:pct(100*quantile(erosion,.95)),
   maxCollateralLossExPremiumPct:pct(100*Math.max(...erosion)),
   meanForwardReturnPct:pct(100*arr.reduce((a,e)=>a+e.futureReturn,0)/arr.length)};
}
const groups={};
for(const [name,filter]of Object.entries(filters)){
 const group=events.filter(filter);groups[name]={overlapping:{},nonoverlappingEvery21Sessions:{}};
 for(const d of [.1,.2,.3]){
  const label=String(Math.round(d*100))+'pct_OTM';
  groups[name].overlapping[label]=sample(group,d);
  groups[name].nonoverlappingEvery21Sessions[label]=sample(group.filter(e=>e.disjointGrid),d);
 }
}
const examples=[0,35,50,60,70,80].map(underlying=>{
 const strike=70,contracts=5,premiumPerShare=1.42;
 const cashReserve=contracts*100*strike,premium=contracts*100*premiumPerShare;
 const payoff=premium-Math.max(0,strike-underlying)*contracts*100;
 return {underlyingAtExpiry:underlying,profitUsd:payoff,profitPctCollateral:pct(100*payoff/cashReserve)};
});
const report={schema_version:1,kind:'CSP_UNDERLYING_BARRIER_STUDY_NOT_OPTION_PNL',
 source_sha256:src.snapshot_sha256,first:events[0].date,last:events.at(-1).date,
 numberOfOverlappingWindows:events.length,horizonSessions:H,
 groups,videoSingleTradeIllustration:{
  claim:'5 contracts, 2025-11-21 $70 put, $1.42 premium per share (unverified single trade)',
  reservedCashUsd:35000,grossPremiumUsd:710,breakevenStrikeLessPremium:68.58,
  expirationScenarios:examples,
  caveat:'Only one short-put leg, ignoring protective put, rolls, commissions, early assignment and shares.'
 },
 limitations:[
  'No historical option chain NBBO/bid-ask premiums; NO option strategy CAGR calculated.',
  'Underlying TQQQ observed ADJUSTED prices; cannot backfill historical strikes or contract multiplier at corporate-action dates.',
  '20% out-of-money is a scenario fixed across each observation, NOT the creator support-based selection.',
  'In-the-money at future day 21 is a payoff risk proxy, not actual early assignment probability.',
  'Daily forward windows heavily overlap. Every-21-session subgrid is only sensitivity.',
  'No modeled short-put cash flow, purchased protection, assignment, roll debits/credits or tax.',
  'StockLens zero-exposure days are not risk-free if short put positions are added; this explicitly probes those days.'
 ],
 optionsChainAvailable:false,actualPutReturnsModeled:false,realUnderlyingObserved:true,
 baselineFrozen:true,noBrokerOrders:true,prodUnchanged:true,autoPromotion:false};
if(groups.all.overlapping['20pct_OTM'].n!==N-START-H)throw Error('COUNT');
if(examples[0].profitUsd!==-34290||examples[2].profitUsd!==-9290||examples[4].profitUsd!==710)throw Error('PAYOFF');
console.log(JSON.stringify(report,null,2));

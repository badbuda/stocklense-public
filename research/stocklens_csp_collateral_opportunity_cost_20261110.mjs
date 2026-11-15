/**
 * Capital opportunity cost of reserving cash collateral for put options
 * on top of StockLens 8.0. This test purposefully has ZERO options premiums.
 * It isolates the capital diverted from frozen 8.0 and is not an options
 * performance backtest or evidence of profitable short-put selling.
 *
 * Spot source: immutable observed TQQQ/QQQ daily adjusted OPEN/CLOSE.
 * Trading: same next-OPEN 2bps fee / 10bps slippage, whole shares.
 */
import {readFileSync} from 'node:fs';
const src=JSON.parse(readFileSync('research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json','utf8'));
const records=src.daily,START=200,N=records.length,STARTING=100000;
if(N!==4191||src.snapshot_sha256!=='bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129')throw Error('INPUT_CHANGED');
function simulate(reserve){
 if(![0,.1,.15,.25,.35].includes(reserve))throw Error('NOT_PREDECLARED');
 let cash=STARTING,q=0,t=0,prev=null,tradeCount=0,notional=0,eqSeries=[];
 for(let i=START;i<N;i++){
  const bar=records[i],lev=bar.l;
  if(prev===null||prev!==lev){
   const equity=cash+q*bar.qo+t*bar.to;
   const tPart=lev>0?(lev-1)/2:0,qPart=lev>0?1-tPart:0;
   const frac=lev===0?0:(.985-reserve);
   const targetQ=Math.floor(equity*qPart*frac/bar.qo),targetT=Math.floor(equity*tPart*frac/bar.to);
   function transact(kind,qty,price,buy){
    qty=Math.floor(Math.max(0,qty));
    if(!buy)qty=Math.min(qty,kind==='q'?q:t);
    if(buy)qty=Math.min(qty,Math.floor(Math.max(0,cash)/(price*1.001*1.0002)));
    if(!qty)return;
    const gross=qty*price;
    cash+=buy?-gross*1.001*1.0002:gross*.999*.9998;
    if(kind==='q')q+=buy?qty:-qty;else t+=buy?qty:-qty;
    tradeCount++;notional+=gross;
   }
   transact('q',q-targetQ,bar.qo,false);
   transact('t',t-targetT,bar.to,false);
   transact('q',targetQ-q,bar.qo,true);
   transact('t',targetT-t,bar.to,true);
  }
  const eq=cash+q*bar.qc+t*bar.tc;
  if(!Number.isFinite(eq)||eq<=0||cash<-.00001)throw Error('BAD_LEDGER');
  eqSeries.push(eq);prev=lev;
 }
 let peak=STARTING,dd=0;
 for(const eq of eqSeries){peak=Math.max(peak,eq);dd=Math.min(dd,eq/peak-1);}
 const years=(Date.parse(records.at(-1).date)-Date.parse(records[START].date))/(365.2425*86400000);
 return {reserve_fraction_at_state_transition:reserve,
  investments_fraction_of_equity_when_on:.985-reserve,
  ending_equity: eqSeries.at(-1),
  cagr:(eqSeries.at(-1)/STARTING)**(1/years)-1,maxdd:dd,
  executed_transactions:tradeCount,executed_notional: notional};
}
const models=[0,.1,.15,.25,.35].map(simulate),base=models[0];
if(base.executed_transactions!==127||Math.abs(base.cagr-.39835414489537446)>1e-9||Math.abs(base.maxdd-(-.4907616145480055))>1e-9)throw Error('BASELINE_PARITY_FAILED');
const comparisons=models.map(x=>({...x,terminal_drag_fraction:1-x.ending_equity/base.ending_equity,
 delta_cagr_pp:(x.cagr-base.cagr)*100,maxdd_delta_pp:(x.maxdd-base.maxdd)*100}));
console.log(JSON.stringify({
 schema_version:1,kind:'CSP_CASH_COLLATERAL_OPPORTUNITY_COST_PREMIUM_FREE',
 source_hash:src.snapshot_sha256,
 period:{from:records[START].date,to:records.at(-1).date,session_count:N-START},
 baseline_model_verified:true,
 money_funded_equally_from_100k:true,
 options_premiums:false,option_chain_quotes:false,option_in_the_money_hedge_returns:false,
 method:'Each original exposure change rebalance into QQQ/TQQQ using 98.5% minus reserved equity percentage. No intra-state rebalancing; cash reserved at every baseline exposure transition; zero interest on cash. Executed next observed adjusted OPEN, 2bps commission and 10bps slippage each side, whole shares.',
 warning:'Not 15% of original cash throughout or continuously 15% of daily equity. Since reserve drifts between state changes, this is an opportunity-cost estimate and NOT a complete daily collateral risk model.',
 models:comparisons, no_capital_deployed:true,no_model_promotion:true,no_prod_changes:true,
},null,2));

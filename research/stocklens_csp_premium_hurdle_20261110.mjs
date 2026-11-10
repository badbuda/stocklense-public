/**
 * Cash-secured TQQQ put "premium hurdle" — observed underlying data only.
 * This is NOT a historical option strategy backtest. There are no historical
 * option quotes, rolls, long hedges or fill times in the frozen source.
 * An exercise cash-collateral hurdle is mathematically calculated at fixed
 * hypothetical OTM strike and a 21-trading-session horizon.
 */
import {readFileSync} from 'node:fs';
const data=JSON.parse(readFileSync('research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json','utf8'));
const r=data.daily,S=200,H=21;
const SNAP='bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129';
if(r.length!==4191||data.snapshot_sha256!==SNAP)throw Error('SOURCE_REPLACED');
function pct(a){return Math.round(a*1e4)/1e4;}
function quantile(v,q){if(!v.length)return null;const a=[...v].sort((x,y)=>x-y),pos=(a.length-1)*q,lo=Math.floor(pos),hi=Math.ceil(pos);return a[lo]*(hi-pos)+a[hi]*(pos-lo);}
const events=[];
for(let i=S;i+H<r.length;i++){
  let b=r[i],open=b.to,expiry=r[i+H].tc;
  if(!(open>0&&expiry>0)||!([0,1.25,2,3].includes(b.l)))throw Error('PRICE_OR_SIGNAL_INVALID');
  events.push({date:b.date,state:b.l,open,expiry,disjoint:(i-S)%H===0});
}
const groups={
 all:e=>true,
 frozen_cash_0x:e=>e.state===0,
 frozen_risk_on:e=>e.state>0,
 frozen_3x:e=>e.state===3,
 bear_2022:e=>e.date.startsWith('2022'),
 bear_2022_frozen_cash:e=>e.date.startsWith('2022')&&e.state===0,
 rally_2024:e=>e.date.startsWith('2024')
};
function aggregate(rows,discount,hypotheticalPremium){
 const y=rows.map(e=>{
  const strike=e.open*(1-discount);
  const intrinsic=Math.max(0,strike-e.expiry)/strike;
  return {intrinsic, itm:intrinsic>0};
 });
 if(!y.length)return {windows:0,blocked_no_sample:true};
 const losses=y.map(z=>z.intrinsic);
 let avg=losses.reduce((a,b)=>a+b,0)/losses.length;
 const win=losses.filter(a=>a>0).length;
 const sorted=[...losses].sort((a,b)=>a-b);
 return {
  windows:y.length,
  expiry_below_strike_pct:pct(win*100/y.length),
  mean_intrinsic_hurdle_pct_of_cash_collateral:pct(avg*100),
  p95_intrinsic_hurdle_pct_of_cash_collateral:pct(quantile(losses,.95)*100),
  worst_intrinsic_hurdle_pct_of_cash_collateral:pct(sorted.at(-1)*100),
  mean_shortfall_pct_of_collateral_if_illustrative_premium:pct((avg-hypotheticalPremium)*100),
  historical_quote_premiums_known:false,
  note:'Hurdle is average payoff liability excluding option premium; shortfall assumes the SAME hypothetical premium on every candidate date, not historical option prices or a tradable return.'
 };
}
const quotedVideoPremium=1.42/70;
const out={
 kind:'STOCKLENS_CSP_PREMIUM_REQUIRED_NOT_OPTION_BACKTEST',
 asof:data.period.end,
 observed_tqqq_ohlc_source_sha:data.snapshot_sha256,
 cohort:{start:events[0].date,end:events.at(-1).date,window_trade_sessions:21,overlapping_total:events.length},
 hypothetical_strike_distances:[.1,.2,.3],
 illustrative_fixed_premium_fraction:quotedVideoPremium,
 illustrative_premium_source:'One narrated five-contract trade: 1.42/70; not observed for other dates',
 groups:Object.fromEntries(Object.entries(groups).map(([name,filter])=>{
   let arr=events.filter(filter);
   return [name,Object.fromEntries([.1,.2,.3].map(d=>{
    const label=Math.round(d*100)+'pct_otm';
    return [label,{
      overlapping:aggregate(arr,d,quotedVideoPremium),
      disjoint_grid:aggregate(arr.filter(e=>e.disjoint),d,quotedVideoPremium)
    }];
   }))];
 })),
 no_price_chain_data:true,
 no_option_returns_modelled:true,
 no_collateral_comparing_real_options_equity:true,
 baseline_8_0_untouched:true,
 no_broker_orders:true,no_production_mutations:true,no_promotion:true,
 strict_limitations:[
  'Observed real adjusted ETF prices only, hypothetical normalized strike: not an actual historical tradable listed option contract.',
  'NO historical trade premiums, bid-ask fills, bid/ask size, long puts, rolling, early assignment, adjusted contract multipliers, FX, taxes or financing.',
  'Each daily-start forward window overlaps; nonoverlap fixed cohort has small per-regime sample. Ex post average intrinsic is not an ex ante risk premium.',
  'Fixed 1.42/70 premium is the narrated price for ONE 2025 trade, not a validated monthly average or trading return. Hypothetical mean shortfall must never be labeled as actual PnL.',
  'Cash-secured put exposure during frozen StockLens 0x cash state BREAKS its defensive posture: held cash is collateral but option has downside.'
 ]
};
if(out.cohort.overlapping_total!==3970)throw Error('WINDOW_COUNT_CHANGED');
if(out.groups.all['20pct_otm'].overlapping.windows!==3970)throw Error('GROUP_INVALID');
console.log(JSON.stringify(out,null,2));

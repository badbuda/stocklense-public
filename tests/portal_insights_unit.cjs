/* Fail-closed offline tests for the customer analytics; no browser or AWS required. */
const assert=require('node:assert/strict');
const fs=require('node:fs');
(async()=>{
 const source=fs.readFileSync('docs/portal-insights.js','utf8');
 const m=await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
 const trade={
   execution_session:'2026-10-08',signal_date:'2026-10-07',symbol:'TQQQ',
   side:'BUY',qty:1197,time_et:'09:32',reference_price:82.2699966430664,
   modeled_fill_price:82.35226663970947,fee:19.715132633546446,
   modeled_slippage_cost:98.47718598174681,fee_bps:2
 };
 const paper={equity_history:[{date:'2026-10-08',equity:97427.96316081587}]};
 const detail=m.inspectTrade(trade,paper);
 assert.equal(detail.buy,true);
 assert.equal(detail.cards[0][1],'2026-10-07');
 assert.equal(detail.cards[1][1],'2026-10-08 · 09:32');
 assert.ok(Math.abs(detail.costTotal-(19.715132633546446+98.47718598174681))<1e-6);
 assert.ok(detail.cards.some(x=>x[0].includes('שווי התיק')));
 assert.throws(()=>m.inspectTrade({...trade,modeled_fill_price:-1},paper),/INVALID_MODELED_TRADE_PRICES/);
 assert.throws(()=>m.inspectTrade({...trade,side:'SELL',qty:0},paper),/INVALID_MODELED_TRADE_PRICES/);

 const yahoo={updated_session:'2026-10-13',daily:[
  {date:'2026-10-08'}, {date:'2026-10-09'}, {date:'2026-10-12'},{date:'2026-10-13'}]};
 const gap=m.forwardGapReport({equity_history:[
  {date:'2026-10-08'},{date:'2026-10-12'},{date:'2026-10-13'}],
  latest:{session_date:'2026-10-13'}},yahoo);
 assert.deepEqual(gap.missingBetween,['2026-10-09']);
 assert.equal(gap.status,'GAPS_OR_DUPLICATES');
 const waiting=m.forwardGapReport({equity_history:[{date:'2026-10-08'}],
   latest:{session_date:'2026-10-08'}},yahoo);
 assert.deepEqual(waiting.pending,['2026-10-09','2026-10-12','2026-10-13']);
 assert.equal(waiting.status,'AWAITING_PUBLICATION');
 assert.equal(m.forwardGapReport({equity_history:[{date:'2026-10-08'}]},null).status,
  'UNVERIFIED_EXCHANGE_CALENDAR');

 const a={strategy:125000,paid:110000,dd:-.2,fees:50,slippage:80,events:[1,2]};
 const b={strategy:160000,paid:145000,dd:-.3,fees:60,slippage:120,events:[1,2,3]};
 const result=m.compareScenarioData(a,b);
 assert.equal(result.deltaEquity,35000);
 assert.equal(result.deltaNetProfit,0,'More contributions must never be presented as better alpha');
 assert.equal(result.rows.length,7);
 console.log('PORTAL_INSIGHTS_UNIT_PASS: trade costs, historical gaps, pending sessions and capital-adjusted A/B comparison');
})().catch(e=>{console.error(e);process.exitCode=1});

import assert from 'node:assert/strict';
import {taxFeedView,taxActionSignal,createNominalTaxBook,recordNominalBuy,recordNominalSale,nominalTerminalLiquidation,reconcileNominalTaxScenario,TAX_PLACEHOLDER} from '../docs/portal-tax.mjs';

assert.equal(taxFeedView(null).ready,false);
assert.equal(taxFeedView({kind:'STOCKLENS_TAX_STATUS_V1',schema_version:1,status:'BLOCKED'}).ready,false);
const complete={kind:'STOCKLENS_TAX_STATUS_V1',schema_version:1,
 status:'RESEARCH_COMPLETE',source:'PRIVATE_SHA_VERIFIED_ST_PAPER',
 asof_date:'2026-11-04',receipt_sha256:'a'.repeat(64),
 fx_verified:true,lot_history_verified:true,broker_withholding_verified:false,
 capital_trading_authorized:false,gross_paper_nav_usd:100000,
 estimated_after_tax_liquidation_usd:99000,estimated_tax_assessed_ils:3000};
assert.equal(taxFeedView(complete,'2026-11-04',100000).ready,true);
assert.equal(taxFeedView(complete,'2026-11-04',100001).ready,false,'mismatched Paper NAV blocks private net estimate');
assert.equal(taxFeedView(complete,'2026-11-05',100000).ready,false,'stale tax data cannot be attached to another Paper day');
assert.equal(taxFeedView({...complete,fx_verified:false},'2026-11-04',100000).ready,false);
assert.equal(taxFeedView({...complete,receipt_sha256:'wrong'},'2026-11-04',100000).ready,false);
assert.equal(taxFeedView({...complete,broker_withholding_verified:true},'2026-11-04',100000).ready,false);
assert.equal(taxFeedView({...complete,estimated_after_tax_liquidation_usd:110000},'2026-11-04',100000).ready,false);
assert.match(TAX_PLACEHOLDER,/לא חושב/);
assert.match(taxActionSignal({defense_active:true}),/ממש/);
assert.match(taxActionSignal({action:'NO_CHANGE'}),/איזון/);
const t=createNominalTaxBook();
recordNominalBuy(t,'TQQQ',10,100,2); // basis 100.20/share
const first=recordNominalSale(t,'TQQQ',5,120,1,.25);
assert.equal(Math.round(first.realized*100)/100,98);
assert.equal(Math.round(first.tax*100)/100,24.5);
assert.equal(t.lots.TQQQ.reduce((n,x)=>n+x.qty,0),5);
const terminal=nominalTerminalLiquidation(t,{QQQ:0,TQQQ:5},{QQQ:100,TQQQ:120},0,10,.25);
assert.ok(terminal.value<600&&terminal.value>500);
assert.ok(Number.isFinite(terminal.netFriction)&&terminal.netFriction>0,
  'real liquidation helper must return its sale friction, not just a fixture');
const linked=reconcileNominalTaxScenario(700,{
  strategy:600,modeled_tax_paid_usd:t.paid,terminal_strategy:terminal
});
assert.ok(Number.isFinite(linked.capitalPathEffect));
assert.ok(Math.abs(linked.untaxedNav-linked.modeledTaxesPaid-linked.capitalPathEffect-
  linked.terminalExitCosts-linked.terminalTax-linked.afterTaxExitValue)<.01);
assert.equal(t.lots.TQQQ[0].qty,5,'hypothetical final sale cannot mutate actual lots');
const loss=recordNominalSale(t,'TQQQ',5,80,0,.25);
assert.equal(loss.tax,0);
assert.ok(t.lossCarry>0);
recordNominalBuy(t,'QQQ',1,100,0);
const offset=recordNominalSale(t,'QQQ',1,110,0,.25);
assert.equal(offset.tax,0,'eligible loss offsets later gain in research stress');
assert.throws(()=>recordNominalSale(createNominalTaxBook(),'QQQ',1,100,0),/TAX_LOTS_INCOMPLETE/);
const large=17688959.18810451,scenario={
 strategy:6516182.823296777,modeled_tax_paid_usd:2445509.9277704824,
 terminal_strategy:{value:6508466.5425494,additionalTax:0,netFriction:7716.2807473775465}
};
const bridge=reconcileNominalTaxScenario(large,scenario);
assert.equal(Math.round(bridge.capitalPathEffect),8727266);
assert.equal(Math.round(bridge.totalGap),11180493);
assert.equal(Math.round(bridge.afterTaxExitValue),6508467);
assert.equal(bridge.terminalTax,0,'never invent a second exit-tax charge');
assert.ok(Math.abs(large-bridge.modeledTaxesPaid-bridge.capitalPathEffect-
    bridge.terminalExitCosts-bridge.terminalTax-bridge.afterTaxExitValue)<.01);
assert.throws(()=>reconcileNominalTaxScenario(large,{...scenario,terminal_strategy:{...scenario.terminal_strategy,netFriction:NaN}}),/INVALID_TAX_BRIDGE_INPUT/);
console.log('PORTAL_TAX_FAIL_CLOSED_AND_NOMINAL_USD_TESTS_PASS');

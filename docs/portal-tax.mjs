/* StockLens tax layer. Public status is fail-closed; USD simulation is only
   a nominal 25% research stress, NEVER verified Israeli personal tax.
   No local storage, broker credentials or side-effecting requests. */
const SHA=/^[0-9a-f]{64}$/i;
const DAY=/^20\d\d-\d\d-\d\d$/;
const amt=x=>typeof x==='number'&&Number.isFinite(x)&&x>=0;
export const TAX_PLACEHOLDER='לא חושב — חסרים נתוני מס מאומתים';

export function taxFeedView(feed, paperSession=null, paperGross=null){
  const blocked={ready:false,status:'BLOCKED',label:TAX_PLACEHOLDER,
    reason:'נדרשים רצף עסקאות מלא, מנות רכישה, שערי מט"ח מתוארכים ואימות מס מול הברוקר.',
    afterTax:null,taxIls:null,sourceDate:null};
  if(!feed||feed.kind!=='STOCKLENS_TAX_STATUS_V1'||feed.schema_version!==1)return blocked;
  if(feed.status==='BLOCKED')return {...blocked,reason:String(feed.reason||blocked.reason)};
  // Only a private, fully traced research snapshot may surface amounts.
  if(feed.status!=='RESEARCH_COMPLETE'||feed.source!=='PRIVATE_SHA_VERIFIED_ST_PAPER'
    ||feed.fx_verified!==true||feed.lot_history_verified!==true
    ||feed.broker_withholding_verified!==false||feed.capital_trading_authorized!==false
    ||!DAY.test(feed.asof_date||'')||!SHA.test(feed.receipt_sha256||'')
    ||!amt(feed.gross_paper_nav_usd)||!amt(feed.estimated_after_tax_liquidation_usd)
    ||!amt(feed.estimated_tax_assessed_ils)
    ||feed.estimated_after_tax_liquidation_usd>feed.gross_paper_nav_usd
    ||paperSession!==feed.asof_date||!amt(paperGross)||
    Math.abs(feed.gross_paper_nav_usd-paperGross)>0.02)return blocked;
  return {ready:true,status:'RESEARCH_COMPLETE',label:'הערכת מס מחקרית · לא ניכוי ברוקר',
    reason:'מזומן אחרי מימוש רעיוני, בהנחות מס מחקריות ואחרי בדיקת מסמך מקור SHA.',
    afterTax:feed.estimated_after_tax_liquidation_usd,
    taxIls:feed.estimated_tax_assessed_ils,sourceDate:feed.asof_date};
}
export function taxActionSignal(signal){
  if(!signal||typeof signal!=='object')return 'איתות מס: לא ניתן לקבוע';
  const action=signal.action;
  if(signal.defense_active===true||action==='ENTER_CASH_NEXT_SESSION')
    return 'איתות מס: יציאה לחשיפה אפס עשויה לממש רווח או הפסד';
  if(action==='NO_CHANGE')
    return 'איתות מס: אין שינוי יעד; איזון קטן עדיין עשוי לכלול מכירה';
  return 'איתות מס: שינוי חשיפה עשוי לחייב מכירה — המס מחושב רק אחרי עסקה';
}
export function createNominalTaxBook(){
 return {lots:{QQQ:[],TQQQ:[]},lossCarry:0,paid:0,realized:0,sales:0};
}
export function recordNominalBuy(book,symbol,qty,fill,fee){
 if(!book.lots[symbol]||!Number.isInteger(qty)||qty<=0||!amt(fill)||fill===0||!amt(fee))
   throw Error('BAD_NOMINAL_TAX_BUY');
 book.lots[symbol].push({qty,basis:fill+fee/qty});
}
export function recordNominalSale(book,symbol,qty,fill,fee,rate=.25){
 if(!book.lots[symbol]||!Number.isInteger(qty)||qty<=0||!amt(fill)||fill===0||
    !amt(fee)||!amt(rate)||rate>1)throw Error('BAD_NOMINAL_TAX_SELL');
 // Validate inventory in full before mutating any lot.
 const lots=book.lots[symbol];
 if(lots.reduce((n,l)=>n+l.qty,0)<qty)throw Error('TAX_LOTS_INCOMPLETE');
 let left=qty,basis=0;
 while(left){
  const lot=lots[0],take=Math.min(left,lot.qty);
  basis+=take*lot.basis;lot.qty-=take;left-=take;
  if(!lot.qty)lots.shift();
 }
 const realized=qty*fill-fee-basis;
 const offset=Math.min(Math.max(0,realized),book.lossCarry);
 const taxable=Math.max(0,realized-offset);
 if(realized<0)book.lossCarry+=-realized;
 else book.lossCarry-=offset;
 const tax=taxable*rate;
 book.paid+=tax;book.realized+=realized;book.sales++;
 return {tax,realized,lossOffset:offset,taxable};
}
export function nominalTerminalLiquidation(book,shares,close,cash,slipBps=10,rate=.25){
 if(!amt(cash)||!amt(slipBps)||slipBps>=10000||!amt(rate)||rate>1)throw Error('BAD_TERMINAL_TAX');
 let netSale=0,remainingGain=0;
 for(const symbol of ['QQQ','TQQQ']){
  const qty=shares[symbol],px=close[symbol],lots=book.lots[symbol];
  if(!Number.isInteger(qty)||qty<0||!amt(px)||px===0)throw Error('BAD_TERMINAL_POSITIONS');
  if(lots.reduce((n,l)=>n+l.qty,0)!==qty)throw Error('TAX_LOTS_POSITION_MISMATCH');
  const proceeds=qty*px*(1-slipBps/10000)*(1-0.0002);
  const basis=lots.reduce((v,l)=>v+l.qty*l.basis,0);
  remainingGain+=proceeds-basis;netSale+=proceeds;
 }
 // Terminal netting is simplified; actual Israeli taxation uses FX and
 // broker-specific lot/annual-offset rules. This is NOT exact tax liability.
 const additionalTax=Math.max(0,remainingGain-book.lossCarry)*rate;
 return {value:cash+netSale-additionalTax,additionalTax,modeledCashTaxPaid:book.paid,
   saleCount:book.sales,realizedUsd:book.realized,
   label:'המחשת 25% דולרית בלבד — לא מס רווחי הון ישראלי מאומת'};
}

/* StockLens customer-facing analytics. No synthetic quotes or broker orders. */
const fmt=new Intl.NumberFormat('en-US',{maximumFractionDigits:2});
const dollars=x=>Number.isFinite(Number(x))?'$'+fmt.format(Number(x)):'—';
const pcent=x=>Number.isFinite(Number(x))?(100*Number(x)).toFixed(2)+'%':'—';
const html=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
const el=id=>document.getElementById(id);
const asNum=x=>{const v=Number(x);return Number.isFinite(v)?v:null};
const card=(label,value,desc)=>'<div class="trade-fact"><small>'+html(label)+'</small><strong>'+html(value)+'</strong><span>'+html(desc)+'</span></div>';

export function inspectTrade(trade,paper){
  const buy=trade.side==='BUY',sell=trade.side==='SELL';
  if(!buy&&!sell)throw Error('UNKNOWN_TRADE_SIDE');
  const qty=asNum(trade.qty),ref=asNum(trade.reference_price),fill=asNum(trade.modeled_fill_price);
  const fee=asNum(trade.fee),slip=asNum(trade.modeled_slippage_cost);
  if(qty===null||qty<=0||ref===null||ref<=0||fill===null||fill<=0)throw Error('INVALID_MODELED_TRADE_PRICES');
  if(fee===null||fee<0||slip===null||slip<0)throw Error('INVALID_TRADE_COSTS');
  const cashImpact=qty*fill+(buy?fee:-fee);
  const days=(paper.equity_history||[]).filter(x=>x.date===trade.execution_session);
  const after=days.length===1?days[0]:null;
  const explain=buy?'המודל הגדיל חשיפה לפי הסיגנל האחרון שהושלם לפני תחילת יום המסחר.':'המודל הקטין חשיפה לפי סיגנל קודם או איזון משקל בתיק.';
  return {
    headline:(buy?'קנייה מדומה':'מכירה מדומה')+' של '+fmt.format(qty)+' יחידות '+trade.symbol,
    explanation:explain,
    cards:[
      ['סיגנל שממנו הגיעה ההחלטה',trade.signal_date||'לא תועד','הסיגנל חייב להקדים את הביצוע; אינו הוראת מסחר אמיתית'],
      ['זמן הביצוע במודל',trade.execution_session+' · '+(trade.time_et||'—'),'שעון ניו־יורק; על בסיס נתוני Yahoo לדקת הפתיחה'],
      ['מחיר מקור / מחיר מדומה',dollars(ref)+' / '+dollars(fill),'פער המחיר הוא הנחת החלקה, לא מילוי בברוקר'],
      ['עלות החלקה לעסקה',dollars(slip),'עלות נפרדת ממחיר הבסיס, כבר כלולה במילוי המדומה'],
      ['עמלת מודל',dollars(fee),'מחושבת לפי הנחת עמלה '+(trade.fee_bps||'—')+' נקודות בסיס'],
      ['סכום קנייה / מכירה ברוטו',dollars(qty*fill),'ללא השוואה ליתרת הברוקר'],
      ['שווי התיק בסיום היום',after?dollars(after.equity):'לא נמצא','סיכום התיק המדומה ביום הביצוע; כולל שינויי מחיר נוספים']
    ],
    costTotal:fee+slip,
    notional:qty*fill,
    buy,sell,cashImpact,
    source:'YFINANCE_1M_RAW'
  };
}

export function showTradeInspector(trade,paper){
 const root=el('paper-trade-detail');
 if(!root)return;
 try{
   const d=inspectTrade(trade,paper);
   root.innerHTML='<div class="trade-inspector-top"><div><h3>'+html(d.headline)+'</h3><p>'+html(d.explanation)+'</p></div><span class="subtle-tag">MODELED · NOT BROKER</span></div>'+
     '<div class="trade-facts">'+d.cards.map(x=>card(...x)).join('')+'</div>'+
     '<p class="trade-evidence">עלות מידול כוללת לעסקה: <strong>'+dollars(d.costTotal)+'</strong>. הנתונים מתייחסים לעסקה מדומה; לא ניתן להסיק מהם רווח או הפסד ממומש לפני סגירת הפוזיציה.</p>';
 }catch(err){root.textContent='נתוני העסקה אינם שלמים: '+err.message;}
}

export function bindTradeInspector(paper){
 const tbody=el('trades-body');
 if(!tbody)return;
 const trades=[...(paper.recent_trades||[])].reverse();
 tbody.querySelectorAll('[data-trade-index]').forEach(row=>{
   const choose=()=>{const i=Number(row.dataset.tradeIndex);if(trades[i])showTradeInspector(trades[i],paper)};
   row.addEventListener('click',choose);
   row.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();choose()}});
 });
 if(trades[0])showTradeInspector(trades[0],paper);
}

export function forwardGapReport(paper,history){
 const dates=(history?.daily||[]).map(row=>row.date);
 const observed=(paper?.equity_history||[]).map(row=>row.date);
 const duplicates=observed.filter((day,index)=>observed.indexOf(day)!==index);
 const errors=[];
 if(duplicates.length)errors.push('כפילות בימים: '+[...new Set(duplicates)].join(', '));
 if(observed.length===0)return {expected:[],missing:[],duplicates,status:'NO_FORWARD_SESSIONS',errors};
 if(dates.length===0)return {expected:[],missing:[],duplicates,status:'UNVERIFIED_EXCHANGE_CALENDAR',errors};
 const begin=observed.reduce((x,y)=>x<y?x:y);
 const latestObserved=observed.reduce((x,y)=>x>y?x:y);
 const lastKnown=history?.updated_session||latestObserved;
 // Include only real exchange sessions that exist in the Yahoo OHLC ledger.
 const expected=dates.filter(d=>d>=begin&&d<=lastKnown);
 const found=new Set(observed);
 const missing=expected.filter(day=>!found.has(day));
 const latest=paper?.latest?.session_date||latestObserved;
 const pending=missing.filter(x=>x>latest);
 const gaps=missing.filter(x=>x<=latest);
 if(gaps.length)errors.push('חסרים בין ימים שפורסמו: '+gaps.join(', '));
 return {expected,missing,missingBetween:gaps,pending,duplicates,
   lastPaper:latest,lastPrice:lastKnown,
   status:errors.length?'GAPS_OR_DUPLICATES':pending.length?'AWAITING_PUBLICATION':'MATCHED_THROUGH_LAST_PRICE_SESSION',
   errors};
}

export function showGapReport(paper,history){
 const d=forwardGapReport(paper,history);
 const node=el('journal-status'),listing=el('journal-gap-list');
 if(!node||!listing)return;
 const stateText=d.status==='MATCHED_THROUGH_LAST_PRICE_SESSION'?
   'אין חורים בין ימי המסחר של Yahoo ליומן Paper עד יום המחירים האחרון שפורסם.':
   d.status==='AWAITING_PUBLICATION'?'יש ימי מסחר שמחיריהם פורסמו ב־Yahoo אך טרם התווספו ליומן Paper. אין להשלים עסקאות בדיעבד.':
   d.status==='NO_FORWARD_SESSIONS'?'עדיין אין רשומות מסחר מדומה.':
   d.status==='UNVERIFIED_EXCHANGE_CALENDAR'?'אין כרגע היסטוריית ימי בורסה מאומתת להשוואה. לא ניתן לקבוע אם יש חורים.':
   'נמצאה חריגה ברצף תיעוד ה־Paper; נדרשת בדיקה.';
 node.textContent=stateText;
 node.classList.toggle('bad',d.status==='GAPS_OR_DUPLICATES');
 listing.innerHTML='<div class="trade-facts">'+[
   card('יום Paper האחרון',d.lastPaper||'—','פרסום GitHub בלבד; אימות DynamoDB בנפרד'),
   card('יום מחירי Yahoo האחרון',d.lastPrice||'—','לפי היסטוריה מאומתת של QQQ ו־TQQQ'),
   card('ימים מאומתים בתיעוד',String((paper.equity_history||[]).length),'לא מספר עסקאות'),
   card('ימים הממתינים לפרסום',String(d.pending?.length||0),'אין מילוי או ביצוע רטרואקטיבי')
 ].join('')+'</div>'+
 (d.errors.length?'<p class="negative">'+d.errors.map(html).join(' · ')+'</p>':'');
}

export function compareScenarioData(a,b){
 const deltaEquity=b.strategy-a.strategy;
 const netA=a.strategy-a.paid,netB=b.strategy-b.paid;
 return {
  deltaEquity,deltaNetProfit:netB-netA,
  rows:[
   ['שווי סופי',dollars(a.strategy),dollars(b.strategy),'שווי נזיל משוער בסוף התקופה'],
   ['סך הפקדות',dollars(a.paid),dollars(b.paid),'הבדל בהפקדות אינו רווח מהאסטרטגיה'],
   ['רווח / הפסד מעל ההפקדות',dollars(netA),dollars(netB),'שווי סופי פחות סך כספים שהופקדו'],
   ['ירידה מרבית',pcent(a.dd),pcent(b.dd),'ירידת שווי מרבית מהשיא בתרחיש'],
   ['עמלות מודל',dollars(a.fees),dollars(b.fees),'עלויות משוערות, לא מסלקת ברוקר'],
   ['עלות החלקה',dollars(a.slippage),dollars(b.slippage),'השפעת הנחת מחיר המילוי'],
   ['עסקאות מחושבות',String(a.events.length),String(b.events.length),'כל עסקה לפי אותן החלטות היסטוריות']
  ]
 };
}

export function updateScenarioComparison(ctx){
 const output=el('scenario-compare-body'),status=el('scenario-compare-status'),empty=el('scenario-compare-empty');
 if(!output||!status)return;
 const {history,a,simulate,draw}=ctx;
 if(!a||!history?.observed_ohlc_available){status.textContent='עדיין אין מחיר TQQQ מאומת ותוצאת תרחיש A.';return}
 try{
  const initial=Number(el('scenario-b-initial').value),monthly=Number(el('scenario-b-monthly').value),slip=Number(el('scenario-b-slip').value);
  if(!Number.isFinite(initial)||initial<100||!Number.isFinite(monthly)||monthly<0||!Number.isFinite(slip)||slip<0)throw Error('קלט לא תקין לתרחיש B.');
  const start=el('sim-start').value,end=el('sim-end').value;
  const rows=history.daily.filter(r=>r.date>=start&&r.date<=end);
  if(rows.length<2)throw Error('יש לבחור לפחות שני ימי מסחר.');
  const b=simulate(rows,initial,monthly,slip);
  const summary=compareScenarioData(a,b);
  output.innerHTML=summary.rows.map(v=>'<tr>'+v.map(c=>'<td>'+html(c)+'</td>').join('')+'</tr>').join('');
  status.textContent='הושוו '+rows.length+' ימי מסחר · אותם מחירי Yahoo ואותן החלטות StockLens קפואות.';
  status.classList.remove('bad');
  const plotted=a.path.map((r,i)=>({date:r.date,s:r.s,q:b.path[i].s}));
  draw('scenario-compare-chart',plotted,['s','q'],false);
  if(empty)empty.hidden=true;
  el('scenario-compare-note').textContent='ירוק: תרחיש A · זהב: תרחיש B. הפרש ברווח מעבר להפקדות: '+
    dollars(summary.deltaNetProfit)+'. ההשוואה אינה תחזית ואין מילויי ברוקר.';
 }catch(error){status.textContent=error.message;status.classList.add('bad');output.innerHTML='';if(empty)empty.hidden=false}
}

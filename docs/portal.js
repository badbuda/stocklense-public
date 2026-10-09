/* StockLens Portal — source-grounded UI only. No broker actions, no invented fill prices. */
import {bindTradeInspector,showGapReport,updateScenarioComparison} from './portal-insights.js';
import {initCloudJournal,refreshCloudJournal} from './portal-cloud.js';
const byId=id=>document.getElementById(id);
const shell=document.getElementById('sidebar');
const fmt=new Intl.NumberFormat('en-US',{maximumFractionDigits:2});
const number=(v,d=2)=>v==null||!Number.isFinite(Number(v))?'—':new Intl.NumberFormat('en-US',{minimumFractionDigits:0,maximumFractionDigits:d}).format(Number(v));
const money=v=>v==null||!Number.isFinite(Number(v))?'—':'$'+fmt.format(Number(v));
const percentage=(v,d=1)=>v==null||!Number.isFinite(Number(v))?'—':(Number(v)*100).toFixed(d)+'%';
const pctRaw=(v,d=1)=>v==null||!Number.isFinite(Number(v))?'—':Number(v).toFixed(d)+'%';
const clean=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const put=(id,value)=>{const e=byId(id);if(e)e.textContent=value};
const setHtml=(id,value)=>{const e=byId(id);if(e)e.innerHTML=value};
const dateText=s=>s?new Intl.DateTimeFormat('he-IL',{year:'numeric',month:'short',day:'numeric',timeZone:'UTC'}).format(new Date(s+'T12:00:00Z')):'—';
const signed=v=>v>0?'positive':v<0?'negative':'';
const PAGE_NAMES={overview:'תמונת מצב',paper:'העסקאות והתיק',performance:'ביצועים וסיכון',simulator:'סימולטור',research:'מעבדת מחקר',evidence:'נתונים ואמינות'};
const state={data:null,series:null,history:null,risk:null,workbench:null,quality:null,exposure:null,lastSimulation:null};
const DATA_ENDPOINTS={data:'data.json',series:'timeseries.json',history:'portal-history.json',risk:'observed_tqqq_risk_audit.json',workbench:'workbench.json',quality:'site_health.json',exposure:'lean-exposure-evidence.json'};
function navigate(page){
  if(!PAGE_NAMES[page])page='overview';
  document.querySelectorAll('.page').forEach(x=>x.classList.toggle('visible',x.dataset.view===page));
  document.querySelectorAll('.nav-item').forEach(x=>{const selected=x.dataset.page===page;x.classList.toggle('selected',selected);if(selected)x.setAttribute('aria-current','page');else x.removeAttribute('aria-current')});
  put('crumb',PAGE_NAMES[page]);put('top-title',PAGE_NAMES[page]);
  shell.classList.remove('open');byId('menu-toggle').setAttribute('aria-expanded','false');
  if(location.hash!=='#'+page)history.replaceState(null,'','#'+page);
  if(page==='simulator'&&state.history&&state.history.observed_ohlc_available&&!state.lastSimulation)runSimulation();
  if(page==='performance')paintPerformance();
  window.scrollTo({top:0,behavior:'instant'});
}
document.querySelectorAll('[data-page], [data-goto]').forEach(x=>x.addEventListener('click',e=>{e.preventDefault();navigate(x.dataset.page||x.dataset.goto)}));
byId('menu-toggle').addEventListener('click',()=>{const isOpen=shell.classList.toggle('open');byId('menu-toggle').setAttribute('aria-expanded',String(isOpen))});
document.addEventListener('keydown',e=>{if(e.key==='Escape'){shell.classList.remove('open');byId('menu-toggle').setAttribute('aria-expanded','false')}});
function readOptional(path){return fetch(path+(path.includes('?')?'&':'?')+'v='+Date.now(),{cache:'no-store'}).then(async r=>{if(!r.ok)throw Error(path+': HTTP '+r.status);return r.json()})}
async function refresh(){
  byId('load-error').hidden=true;put('side-status','טוען נתונים…');
  const keys=Object.keys(DATA_ENDPOINTS);
  const results=await Promise.allSettled(keys.map(x=>readOptional('./'+DATA_ENDPOINTS[x])));
  keys.forEach((key,i)=>{state[key]=results[i].status==='fulfilled'?results[i].value:null});
  if(!state.data||!state.series){byId('load-error').hidden=false;byId('load-error').textContent='לא הצלחתי לטעון את נתוני הבקרה. נסי רענון. נתונים שלא נטענו לא יוצגו כהצלחה.';put('side-status','תקלה בטעינת נתונים');return}
  render();
}
byId('refresh').addEventListener('click',refresh);
function tag(title,desc,value,ok){return '<div class="factor"><div><strong>'+clean(title)+'</strong><small>'+clean(desc)+'</small></div><span class="pill'+(ok?' good':'')+'">'+clean(value)+'</span></div>'}
function render(){
  const d=state.data, sig=d.signal||{}, paper=d.paper||{}, latest=paper.latest||{}, perf=state.risk?.full_path||{}, period=state.risk?.period||{};
  const days=paper.sessions||0, target=Number(sig.tqqq_weight||0), cash=Number(sig.cash_weight||0);
  put('side-status','פרסום אחרון: '+(sig.asof_date||'לא זמין'));
  put('asof-badge','סיגנל '+(sig.asof_date||'חסר'));
  const level=sig.defense_active?'הגנה · מזומן':'רמה '+(sig.level??'—')+' · '+number(sig.target_leverage)+'×';
  put('hero-state',sig.defense_active?'המודל במצב הגנה':sig.action==='NO_CHANGE'?'אין שינוי בחשיפה':'נדרש שינוי בחשיפה');
  put('hero-level',level);
  put('hero-explain',sig.defense_active?'התנאים הפעילו מנגנון הגנה. היעד כעת הוא מזומן, לא קנייה ממונפת.':sig.action==='NO_CHANGE'?'הסיגנל העדכני שומר על רמת החשיפה הקודמת. אין הוראה לברוקר.':'המודל שינה יעד חשיפה; ההחלטה מיועדת לסימולציה של יום המסחר הבא, לא למסחר ישיר.');
  put('hero-tqqq',percentage(target));put('hero-qqq',percentage(sig.qqq_weight));
  put('hero-cash',percentage(cash));
  put('hero-date','לפי נתוני QQQ עד '+dateText(sig.asof_date));
  put('kpi-nav',money(latest.equity));
  const ret=latest.cumulative_return;
  put('kpi-paper-change',ret!=null?percentage(ret,2)+' מאז תחילת התיק המדומה':'אין מספיק נתונים');
  byId('kpi-paper-change').className='metric-delta '+signed(Number(ret));
  put('kpi-days',number(days,0));put('prospective-count',number(days,0));
  put('kpi-trades',number(paper.trades||0,0)+' עסקאות מדומות');
  put('kpi-days-note',days<20?'מוקדם מדי לקבוע אם המערכת מצליחה. נדרשים שבועות וחודשים של תצפית.':'נתונים מדומים קדימה בלבד; עדיין לא ממלאים פערי ברוקר.');
  put('history-cagr',percentage(perf.stocklens_cagr,1));put('history-dd',percentage(perf.stocklens_max_drawdown,1));
  put('paper-nav',money(latest.equity));put('paper-cash',money(latest.cash));put('paper-shares',number(latest.tqqq_shares,0));
  put('paper-fees',money(latest.cumulative_fees));put('paper-slip',money(latest.cumulative_slippage_cost));
  put('perf-cagr',percentage(perf.stocklens_cagr));put('perf-qqq',percentage(perf.qqq_cagr));put('perf-dd',percentage(perf.stocklens_max_drawdown));
  put('perf-period',period.start&&period.end?period.start.slice(0,4)+'–'+period.end.slice(0,4):'—');
  const why=d.why||{}, feat=sig.features||{};
  setHtml('factor-list',[
    tag('מגמה ארוכה', 'QQQ גבוה מהממוצע של 200 יום', percentage(why.close_vs_sma200_pct,1), Number(why.close_vs_sma200_pct)>0),
    tag('תנודתיות 20 יום', 'תנודתיות שנתית מחושבת מהמחירים האחרונים',percentage(feat.vol20,1),Number(feat.vol20)<.28),
    tag('מומנטום 12 חודשים','מבט על שינוי המחיר לאורך שנה',percentage(feat.mom12,1),Number(feat.mom12)>0),
    tag('רמת הגנה', 'הגנה מופעלת לפי כללי המודל הקפוא',sig.defense_active?'פעילה':'כבויה',!sig.defense_active)
  ].join(''));
  const equity=paper.equity_history||[];
  if(equity.length>=2){
    drawChart('paper-chart',equity.map(x=>({date:x.date,s:x.equity})),['s'],false);
    byId('paper-chart-empty').hidden=true;
  }else{
    byId('paper-chart').replaceChildren();byId('paper-chart-empty').hidden=false;
    byId('paper-chart-empty').textContent=equity.length===1?'יש לנו יום מדומה אחד בלבד. אחרי שיצטברו עוד ימים יופיע כאן גרף אמיתי, ללא קו שהומצא.':'עדיין אין ימי Paper Trading מאומתים.';
  }
  put('paper-chart-caption',equity.length+' ימי תיעוד · מקור: יומן Paper · לא מסחר בברוקר');
  renderTrades();showGapReport(paper,state.history);renderResearch();renderRisk();renderHealth();renderGovernance(d);
  setupSimulation();
  paintPerformance();
}
function renderGovernance(d){
  const capital=d.capital_readiness||{},qc=d.qc_frozen_record||{},paper=d.paper||{}, latest=paper.latest||{}, perf=d.performance||{};
  const original=Number(latest.equity),cum=Number(latest.cumulative_return),hasPaper=latest.equity!=null&&latest.cumulative_return!=null;
  const technical=capital.technical_checks_pass===true,auto=capital.automatic_trading_authorized===true;
  const parity=capital.full_lean_execution_parity===true && d.qc_parity_dossier?.same_input_evidence?.proven===true;
  put('real-paper-sessions',number(paper.sessions,0));
  put('research-session-count',number(capital.prospective_completed_sessions,0));
  put('real-paper-return',hasPaper?percentage(cum,2):'אין נתון');
  byId('real-paper-return').className=hasPaper?signed(cum):'';
  const baseline=hasPaper&&cum>-1?original/(1+cum):null;
  put('real-paper-baseline',baseline!=null?'מאז '+money(baseline)+' שהושקעו, כולל יום הכניסה':'מועד הבסיס אינו מאומת');
  put('model-parity-state',parity?'מאומת':'טרם הוכח');
  const reasons=[];
  if(!technical)reasons.push('בדיקות מוכנות ההון אינן עוברות במלואן');
  if(!parity)reasons.push('זהות קלט ומחירי ביצוע מול LEAN המקורי טרם הוכחו');
  if(!auto)reasons.push('שליחת הוראות לברוקר אינה מורשית');
  put('readiness-message',reasons.length?reasons.join(' · '):'גם כשהבדיקות הטכניות עוברות, אין המלצת השקעה או הרשאה למסחר אוטומטי.');
  const cockpit=d.execution_cockpit||{},planned=(cockpit.orders||[]).filter(x=>x.dry_run===true);
  const singleShare=planned.some(x=>x.symbol==='TQQQ'&&Number(x.quantity)===1);
  const inconsistent=hasPaper&&perf.sessions===paper.sessions&&
     perf.total_return_pct!=null&&Math.abs(Number(perf.total_return_pct)-100*cum)>0.1;
  setHtml('capital-readiness-details',[
    tag('מוכנות הון טכנית','בדיקות האות, נתונים והצלבת הסימולטור',technical?'עבר':'חסום',technical),
    exposureEvidenceTag(),
    tag('זהות מלאה מול LEAN','זהות קלט, קוד וביצוע; שונה מהתאמת חשיפה יומית',parity?'הוכחה':'לא הוכחה',parity),
    tag('מסחר אמיתי','האם יש הרשאה לשלוח הוראות אוטומטיות',auto?'הרשאה קיימת':'אסור',false),
    tag('שני מוני מחקר נפרדים','Paper: '+(paper.sessions??'—')+' · מחקר: '+(capital.prospective_completed_sessions??'—'),'לא אותו ניסוי',false),
    tag('פער בין מדדי תשואה',inconsistent?'performance מראה '+number(perf.total_return_pct)+'%, ו־ledger מראה '+percentage(cum,2):'ללא פער מזוהה',inconsistent?'קיים — הצגה לפי ledger':'לא זוהה',!inconsistent),
    tag('אי־התאמה בפקודות Dry Run',singleShare?'קיים תכנון למכירת מניית TQQQ אחת — ללא הוראה לברוקר':'אין דוגמת חריגה של מניה בודדת',singleShare?'דורש סבילות/יישוב יעדים':'מעקב בלבד',!singleShare)
  ].join(''));
}
function renderTrades(){
  const paper=state.data.paper||{}, tr=paper.recent_trades||[], rows=paper.equity_history||[];
  put('trades-count',number(paper.trades||tr.length,0)+' עסקאות');
  setHtml('trades-body',tr.length?[...tr].reverse().map((t,i)=>'<tr tabindex="0" role="button" aria-label="פירוט עסקת '+clean(t.symbol)+'" data-trade-index="'+i+'"><td>'+clean(t.execution_session)+'</td><td><span class="research-status '+(t.side==='BUY'?'accepted':'rejected')+'">'+clean(t.side==='BUY'?'קנייה':t.side==='SELL'?'מכירה':t.side)+'</span></td><td>'+clean(t.symbol)+'</td><td>'+number(t.qty,0)+'</td><td>'+clean(t.time_et)+'</td><td>'+money(t.reference_price)+'</td><td>'+money(t.modeled_fill_price)+'</td><td>'+money(t.fee)+'</td><td>'+clean(t.signal_date)+'</td></tr>').join(''):'<tr><td colspan="9">עדיין אין פעולות מתועדות ביומן.</td></tr>');
  bindTradeInspector(paper);
  setHtml('paper-body',rows.length?[...rows].reverse().map(t=>'<tr><td>'+clean(t.date)+'</td><td>'+money(t.equity)+'</td><td class="'+signed(Number(t.return))+'">'+percentage(t.return,2)+'</td><td class="'+signed(Number(t.drawdown))+'">'+percentage(t.drawdown,2)+'</td></tr>').join(''):'<tr><td colspan="4">אין עדיין יומן הון.</td></tr>');
}
function renderResearch(){
  const ex=state.workbench?.research_comparison?.experiments||[];
  setHtml('experiments',ex.length?ex.map(item=>{
    const status=String(item.governance_status||item.result_status||'לא ידוע'),cl=/REJECT/i.test(status)?'rejected':/PASS|ACCEPT/i.test(status)?'accepted':'';
    return '<article class="experiment"><h3>'+clean(item.name||item.experiment_id)+'</h3><span class="research-status '+cl+'">'+clean(status)+'</span><p>'+clean(item.governance_reason||'אין אישור אוטומטי להחלפת האסטרטגיה הקפואה.')+'</p></article>'
  }).join(''):'<p class="muted">נתוני המחקר עדיין אינם זמינים בקובץ שנטען.</p>');
}
function renderRisk(){
  const years=state.risk?.calendar_years||[];
  setHtml('years-body',years.length?[...years].reverse().map(y=>'<tr><td>'+clean(y.year)+'</td><td class="'+signed(Number(y.stocklens_return))+'">'+percentage(y.stocklens_return)+'</td><td class="'+signed(Number(y.qqq_return))+'">'+percentage(y.qqq_return)+'</td><td class="'+signed(Number(y.stocklens_return)-Number(y.qqq_return))+'">'+percentage(Number(y.stocklens_return)-Number(y.qqq_return))+'</td></tr>').join(''):'<tr><td colspan="4">אין נתוני סיכון תקפים.</td></tr>');
}
function exposureEvidenceTag(){
  const e=state.exposure;
  const verified=e?.status==='VERIFIED_CROSS_PROVIDER_EXPOSURE_ALIGNMENT_NOT_LEAN_INPUT_PARITY'
     &&e?.kind==='LEAN_SL724_ORIGINAL_VS_YAHOO_QQQ_TQQQ_PRIOR_SIGNAL_EXECUTION_EXPOSURE'
     &&Number.isInteger(e?.overlap_sessions)&&e.overlap_sessions>0
     &&Number.isInteger(e?.matching_exposures)&&e.matching_exposures<=e.overlap_sessions
     &&e.matching_exposures>=0
     &&Math.abs(e.daily_exposure_match_rate-e.matching_exposures/e.overlap_sessions)<1e-9
     &&e.full_same_input_parity_proven===false;
  if(!verified)return tag('LEAN מול Yahoo — חשיפה יומית','עדות השוואת ספקים לא נטענה או לא אומתה','לא מאומת',false);
  return tag('LEAN מול Yahoo — חשיפה יומית','התאמה בחשיפה בלבד, לא זהות קלט או מילוי בברוקר; '+e.matching_exposures+'/'+e.overlap_sessions+' ימים',percentage(e.daily_exposure_match_rate,2),'cross-provider');
}
function renderHealth(){
 const d=state.data,sig=d.signal||{},paper=d.paper||{},v=state.history;
 setHtml('health-list',[
  exposureEvidenceTag(),
 tag('סיגנל יומי', 'מבוסס על סגירת QQQ האחרונה שהושלמה',sig.asof_date||'חסר',!!sig.asof_date),
 tag('תיק Paper', 'מספר ימי מסחר שנרשמו ביומן המודל',String(paper.sessions??'אין'),(paper.sessions||0)>0),
 tag('Yahoo / TQQQ היסטורי', 'עדכון לפי ביצוע משוער בשער פתיחה יומי',v?.updated_session||'עדיין לא נבנה תקציר',!!v?.daily?.length),
 tag('מחירי ETF לסימולטור','רק מחירים של QQQ/TQQQ שנצפו בפועל',v?.observed_ohlc_available?'מאומת מול קובץ המקור':'לא זמין עדיין',!!v?.observed_ohlc_available),
 tag('שלמות נתוני האתר','תקינות יצירת הקבצים; לא הוכחת רווחיות',state.quality?.healthy?'קבצים תקינים':'לא מאומת',!!state.quality?.healthy)
 ].join(''));
}
function svgElement(tag,attributes={},textValue){
 const n=document.createElementNS('http://www.w3.org/2000/svg',tag);
 for(const [k,v] of Object.entries(attributes))n.setAttribute(k,String(v));
 if(textValue!=null)n.textContent=textValue;
 return n;
}
function drawChart(id,rows,series=['s','q'],normalize=true){
 const svg=byId(id);svg.replaceChildren();if(rows.length<2)return false;
 const box=svg.viewBox.baseVal,W=box.width||900,H=box.height||340;
 const pad={t:23,r:18,b:32,l:72};
 const values=rows.flatMap(r=>series.map(k=>Number(r[k]))).filter(Number.isFinite);
 if(!values.length)return false;
 const bounds=series.map(k=>Number(rows[0][k]));
 const mapped=rows.map(r=>Object.fromEntries(series.map((k,i)=>[k,normalize?Number(r[k])/bounds[i]*100000:Number(r[k])])));
 const all=mapped.flatMap(r=>series.map(k=>r[k])).filter(Number.isFinite);
 let min=Math.min(...all),max=Math.max(...all);
 if(min===max){min*=.98;max*=1.02}
 const span=max-min;
 min=Math.max(0,min-span*.09);max=max+span*.12;
 const x=i=>pad.l+i*(W-pad.l-pad.r)/(rows.length-1),y=v=>pad.t+(max-v)/(max-min)*(H-pad.t-pad.b);
 for(let i=0;i<5;i++){const v=min+(max-min)*i/4,Y=y(v);svg.appendChild(svgElement('line',{x1:pad.l,x2:W-pad.r,y1:Y,y2:Y,class:'gridline'}));svg.appendChild(svgElement('text',{x:pad.l-8,y:Y+4,'text-anchor':'end'},'$'+(v/1000).toFixed(0)+'k'))}
 for(const key of series){const pts=mapped.map((r,i)=>Number.isFinite(r[key])?x(i).toFixed(2)+','+y(r[key]).toFixed(2):null).filter(Boolean);svg.appendChild(svgElement('polyline',{points:pts.join(' '),class:key==='q'?'line-gold':'line-sky',fill:'none'}))}
 svg.appendChild(svgElement('text',{x:pad.l,y:H-10},rows[0].date));
 svg.appendChild(svgElement('text',{x:W-pad.r,y:H-10,'text-anchor':'end'},rows.at(-1).date));
 const cursor=svgElement('line',{x1:pad.l,x2:pad.l,y1:pad.t,y2:H-pad.b,stroke:'#9abbd8','stroke-dasharray':'3 4',opacity:0});
 svg.appendChild(cursor);
 const tip=svgElement('text',{x:pad.l,y:pad.t+9,opacity:0,'text-anchor':'start'});
 svg.appendChild(tip);
 const point=e=>{const r=svg.getBoundingClientRect();const px=(e.clientX-r.left)/r.width*W;const i=Math.round((px-pad.l)/(W-pad.l-pad.r)*(rows.length-1));const idx=Math.max(0,Math.min(rows.length-1,i));cursor.setAttribute('x1',x(idx));cursor.setAttribute('x2',x(idx));cursor.setAttribute('opacity','1');tip.setAttribute('opacity','1');tip.setAttribute('x',Math.min(W-220,Math.max(pad.l,x(idx))));tip.textContent=rows[idx].date+' · '+series.map(k=>(k==='q'?'QQQ ':'StockLens ')+money(mapped[idx][k])).join(' / ')};
 svg.addEventListener('pointermove',point,{signal:chartAbort.signal});svg.addEventListener('pointerleave',()=>{cursor.setAttribute('opacity',0);tip.setAttribute('opacity',0)},{signal:chartAbort.signal});
 return true;
}
let chartAbort=new AbortController();
function paintPerformance(){
 if(!state.risk)return;
 chartAbort.abort();chartAbort=new AbortController();
 const h=state.history;
 const empty=byId('performance-chart-empty');
 if(!h||!Array.isArray(h.daily)||h.daily.length<2){byId('performance-chart').replaceChildren();empty.hidden=false;empty.textContent='ההיסטוריה המנורמלת עדיין נבנית מדוח QQQ/TQQQ. התשואות והסיכון המסוכמים מוצגים למעלה, אך לא נצייר גרף בלי נתונים מאומתים.';put('performance-detail','המקור ההיסטורי: '+(state.risk.evidence_scope||'בדיקות QQQ/TQQQ'));return}
 const years=byId('chart-range').value;
 const last=h.daily.at(-1),start=years==='all'?'0000-01-01':String(Number(last.date.slice(0,4))-Number(years))+'-'+last.date.slice(5);
 const rows=h.daily.filter(r=>r.date>=start);
 if(rows.length<2){empty.hidden=false;empty.textContent='אין מספיק ימי מדידה בתקופה שנבחרה';return}
 empty.hidden=true;drawChart('performance-chart',rows,['s','q'],true);
 put('performance-detail',rows.length+' ימי מסחר · '+rows[0].date+' עד '+rows.at(-1).date+' · QQQ/TQQQ מחירי Yahoo מותאמים · ביצוע היסטורי משוער, לא ביצוע ברוקר');
}
byId('chart-range').addEventListener('change',paintPerformance);
function csvCell(v){
 const x=String(v==null?'':v);
 const neutral=/^[\s]*[=+\-@\t\r]/.test(x)?"'"+x:x;
 return '"'+neutral.replace(/"/g,'""')+'"';
}
function downloadCSV(filename,columns,rows){
 const text='\uFEFF'+[columns.join(','),...rows.map(r=>columns.map(c=>csvCell(r[c])).join(','))].join('\r\n')+'\r\n';
 const blob=new Blob([text],{type:'text/csv;charset=utf-8'});
 const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=filename;document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
}
byId('export-trades').addEventListener('click',()=>{const r=state.data?.paper?.recent_trades||[];downloadCSV('stocklens-paper-trades.csv',['execution_session','signal_date','symbol','side','qty','time_et','reference_price','modeled_fill_price','fee','slippage_bps'],r)});
byId('export-paper').addEventListener('click',()=>downloadCSV('stocklens-paper-equity.csv',['date','equity','return','drawdown'],state.data?.paper?.equity_history||[]));
byId('export-summary').addEventListener('click',()=>{const s=state.data?.signal||{},p=state.data?.paper||{};downloadCSV('stocklens-daily-summary.csv',['date','level','leverage','action','modeled_equity','paper_sessions','source'],[{date:s.asof_date,level:s.level,leverage:s.target_leverage,action:s.action,modeled_equity:p.latest?.equity,paper_sessions:p.sessions,source:'QQQ_YAHOO_ADJUSTED_DAILY_CLOSE'}])});
function setupSimulation(){
 const h=state.history;
 if(!h?.daily?.length){put('sim-message','לא קיבלנו עדיין היסטוריה מנורמלת של מחירי ETF. הסימולטור לא יבצע חישוב מלאכותי על בסיס QQQ×3.');return}
 const start=byId('sim-start'),end=byId('sim-end');
 start.min=h.daily[0].date;start.max=h.daily.at(-1).date;end.min=h.daily[0].date;end.max=h.daily.at(-1).date;
 if(!start.value)start.value=h.daily[0].date;
 if(!end.value)end.value=h.daily.at(-1).date;
 put('sim-message',h.observed_ohlc_available?'מוכן · מחירי QQQ ו־TQQQ יומיים שנצפו מ־Yahoo, ותאריך סיגנל קודם לכל יום.':'יש נתוני NAV היסטוריים, אך קובץ OHLC מאומת עדיין חסר. לא נריץ סימולטור עסקאות ללא מחירי TQQQ נצפים.');
}
function weights(l){if(l===0)return {QQQ:0,TQQQ:0};if(l===1.25)return {QQQ:.861875,TQQQ:.123125};if(l===2)return {QQQ:.4925,TQQQ:.4925};if(l===3)return {QQQ:0,TQQQ:.985};throw Error('רמת חשיפה לא מוכרת: '+l)}
function makePortfolio(initial){return {cash:initial,shares:{QQQ:0,TQQQ:0},fees:0,slip:0,peak:initial,dd:0}}
function nav(p,r,field){return p.cash+p.shares.QQQ*Number(r['q'+field])+p.shares.TQQQ*Number(r['t'+field])}
function order(p,r,symbol,side,count,slip,day,cause,events){
 if(count<=0)return;
 const ref=Number(r[(symbol==='QQQ'?'q':'t')+'o']),factor=side==='BUY'?1:-1,fill=ref*(1+factor*slip/10000),fee=count*fill*.0002;
 if(side==='BUY'){const affordable=Math.floor(Math.max(0,p.cash)/ (fill*1.0002));count=Math.min(count,affordable);if(count<=0)return;p.cash-=count*fill*(1.0002);p.shares[symbol]+=count}
 else{count=Math.min(count,p.shares[symbol]);if(count<=0)return;p.cash+=count*fill-fee;p.shares[symbol]-=count}
 p.fees+=count*fill*.0002;p.slip+=count*Math.abs(fill-ref);
 if(events)events.push({date:day,symbol,side,qty:count,modeled_price:fill.toFixed(4),reason:cause});
}
function rebalance(p,r,target,slip,day,cause,events){
 const equity=nav(p,r,'o'),desired={QQQ:Math.floor(equity*target.QQQ/Number(r.qo)),TQQQ:Math.floor(equity*target.TQQQ/Number(r.to))};
 for(const symbol of ['QQQ','TQQQ'])order(p,r,symbol,'SELL',Math.max(0,p.shares[symbol]-desired[symbol]),slip,day,cause,events);
 for(const symbol of ['QQQ','TQQQ'])order(p,r,symbol,'BUY',Math.max(0,desired[symbol]-p.shares[symbol]),slip,day,cause,events);
}
function simulateRealETF(rows,initial,monthly,slip){
 const a=makePortfolio(initial),b=makePortfolio(initial),events=[],path=[];
 let paid=initial,month=null,prev=null,peakA=initial,peakB=initial,ddA=0,ddB=0;
 for(const r of rows){
  const l=Number(r.l),w=weights(l),ym=r.date.slice(0,7);
  const deposit=month!==null&&ym!==month?monthly:0;
  paid+=deposit;a.cash+=deposit;b.cash+=deposit;
  const changed=prev===null||prev!==l;
  if(changed||deposit>0)rebalance(a,r,w,slip,r.date,changed?'שינוי חשיפה / אתחול':'הפקדה חודשית',events);
  if(prev===null||deposit>0)rebalance(b,r,{QQQ:1,TQQQ:0},slip,r.date,'תיק השוואה QQQ',null);
  const av=nav(a,r,'c'),bv=nav(b,r,'c');
  if(av<=0||bv<=0||!Number.isFinite(av+bv))throw Error('שווי תיק לא חוקי ביום '+r.date);
  peakA=Math.max(peakA,av);peakB=Math.max(peakB,bv);
  ddA=Math.min(ddA,av/peakA-1);ddB=Math.min(ddB,bv/peakB-1);
  path.push({date:r.date,s:av,q:bv});
  prev=l;month=ym;
 }
 return {strategy:nav(a,rows.at(-1),'c'),benchmark:nav(b,rows.at(-1),'c'),paid,dd:ddA,benchmark_dd:ddB,fees:a.fees,slippage:a.slip,events,path};
}
function runSimulation(e){
 if(e)e.preventDefault();
 const h=state.history;
 if(!h?.observed_ohlc_available||!h.daily?.length){put('sim-message','חסרים מחירי QQQ/TQQQ מאומתים. לא ניתן לחשב כרגע עסקאות מדומות באופן אמין.');byId('sim-message').classList.add('bad');return}
 try{
  const initial=Number(byId('sim-initial').value),monthly=Number(byId('sim-monthly').value),slip=Number(byId('sim-slip').value);
  const start=byId('sim-start').value,end=byId('sim-end').value;
  if(!Number.isFinite(initial)||initial<100||!Number.isFinite(monthly)||monthly<0||!Number.isFinite(slip)||start>end)throw Error('צריך להזין הון התחלתי חיובי, הפקדה לא שלילית וטווח תאריכים תקין.');
  const rows=h.daily.filter(r=>r.date>=start&&r.date<=end);
  if(rows.length<2)throw Error('בחרי תקופה של שני ימי מסחר לפחות.');
  if(rows.some(r=>['qo','qc','to','tc'].some(k=>!Number.isFinite(Number(r[k]))||Number(r[k])<=0)))throw Error('לסימולציה חסר מחיר ETF מקורי לחלק מהימים.');
  const result=simulateRealETF(rows,initial,monthly,slip);
  state.lastSimulation=result;
  put('sim-strategy',money(result.strategy));put('sim-benchmark',money(result.benchmark));put('sim-paid',money(result.paid));put('sim-dd',percentage(result.dd,1));
  drawChart('sim-chart',result.path,['s','q'],false);byId('sim-chart-empty').hidden=true;
  put('sim-message','חושבו '+number(rows.length,0)+' ימי מסחר · '+number(result.events.length,0)+' אירועי קנייה/מכירה · ללא עסקאות ברוקר.');
  byId('sim-message').classList.remove('bad');
  put('sim-footnote','תוצאה היסטורית מותנית בהנחות: עמלות 2 bps לצד, החלקה '+slip+' bps לצד, מחיר פתיחה יומי מותאם מ־Yahoo. השיטה נשארה קפואה. רמת החשיפה 3× משתמשת ב־TQQQ נצפה, לא ב־QQQ×3.');
  updateScenarioComparison({history:h,a:result,simulate:simulateRealETF,draw:drawChart});
  setHtml('sim-events',result.events.length?result.events.slice(-100).reverse().map(r=>'<tr><td>'+clean(r.date)+'</td><td>'+clean(r.symbol)+'</td><td>'+clean(r.side)+'</td><td>'+number(r.qty,0)+'</td><td>'+money(r.modeled_price)+'</td><td>'+clean(r.reason)+'</td></tr>').join(''):'<tr><td colspan="6">לא נמצאו עסקאות בתקופה הזו.</td></tr>');
 }catch(err){put('sim-message',err.message);byId('sim-message').classList.add('bad')}
}
byId('sim-form').addEventListener('submit',runSimulation);
byId('scenario-b-form').addEventListener('submit',e=>{e.preventDefault();updateScenarioComparison({history:state.history,a:state.lastSimulation,simulate:simulateRealETF,draw:drawChart})});
byId('sim-download').addEventListener('click',()=>downloadCSV('stocklens-historical-modelled-trades.csv',['date','symbol','side','qty','modeled_price','reason'],state.lastSimulation?.events||[]));
initCloudJournal({getHistory:()=>state.history,showGaps:()=>showGapReport(state.data?.paper||{},state.history)});
navigate(location.hash.slice(1)||'overview');refresh();

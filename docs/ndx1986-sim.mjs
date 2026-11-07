/* Standalone NDX index-price 1986 research simulator. Never observed ETF fills. */
const $ = id => document.getElementById(id);
const usd = n => Number.isFinite(n) ? '$'+new Intl.NumberFormat('en-US',{maximumFractionDigits:0}).format(n) : '—';
const pct = n => Number.isFinite(n) ? (100*n).toFixed(1)+'%' : '—';
let source = null;
const weights = l => l===0?[0,0]:l===3?[0,.985]:l===2?[.4925,.4925]:l===1.25?[.861875,.123125]:null;

export function simulateIndexResearch(rows, {initial,monthly,drag,costBps}) {
  if (!Array.isArray(rows) || rows.length<2 || ![initial,monthly,drag,costBps].every(Number.isFinite)
      || initial<100 || monthly<0 || drag<0 || drag>0.3 || costBps<0 || costBps>500)
    throw Error('קלט סימולציית מדד לא תקין');
  if (rows.some(r=>!Number.isFinite(r.close)||r.close<=0||!weights(r.l)))
    throw Error('המחירים או החשיפות במחקר אינם תקינים');
  let cash=initial, one=0, three=0, benchmark=initial, paid=initial;
  let prev=rows[0], lastLevel=null, lastMonth=rows[0].date.slice(0,7), peak=initial, maxDD=0, totalCosts=0;
  const path=[{date:prev.date,s:initial,q:initial}];
  for (const row of rows.slice(1)) {
    if (row.date<=prev.date) throw Error('תאריכי המדד אינם עולים');
    const ret=row.close/prev.close-1;
    const threeRet=3*ret-drag/252; // Synthetic daily-reset sleeve, not TQQQ.
    if (threeRet<=-1) throw Error('מחיקה אפשרית של מוצר ממונף ביום '+row.date+' — המחקר נעצר');
    const ym=row.date.slice(0,7), deposit=ym!==lastMonth?monthly:0;
    cash+=deposit;benchmark+=deposit;paid+=deposit;
    if (lastLevel!==row.l || deposit>0) {
      const [w1,w3]=weights(row.l), equity=cash+one+three;
      const turnover=Math.abs(one-equity*w1)+Math.abs(three-equity*w3);
      const cost=turnover*costBps/10000;
      if (cost>=equity) throw Error('עלויות מסחר גבוהות מההון');
      const net=equity-cost;
      one=net*w1;three=net*w3;cash=net*(1-w1-w3);totalCosts+=cost;
    }
    one*=1+ret;three*=1+threeRet;benchmark*=1+ret;
    const nav=cash+one+three;
    if (![nav,benchmark].every(x=>Number.isFinite(x)&&x>0)) throw Error('שווי הון לא תקין ביום '+row.date);
    peak=Math.max(peak,nav);maxDD=Math.min(maxDD,nav/peak-1);
    path.push({date:row.date,s:nav,q:benchmark});
    prev=row;lastLevel=row.l;lastMonth=ym;
  }
  return {strategy:cash+one+three,benchmark,paid,maxDD,totalCosts,path};
}

function draw(path) {
  const svg=$('ndx86-chart');
  const values=path.flatMap(r=>[r.s,r.q]), min=Math.min(...values),max=Math.max(...values);
  const logMin=Math.log(Math.max(0.01,min)), logMax=Math.log(max);
  const y=v=>240-(Math.log(v)-logMin)/Math.max(0.00001,logMax-logMin)*210;
  const sample=path.filter((_,i)=>i%Math.max(1,Math.ceil(path.length/650))===0||i===path.length-1);
  const line=key=>sample.map((r,i)=>((i?'L':'M')+(30+(path.indexOf(r)/(path.length-1))*840).toFixed(1)+','+y(r[key]).toFixed(1))).join(' ');
  svg.innerHTML='<path d="'+line('s')+'" fill="none" stroke="#65d2f4" stroke-width="2"/>'+
    '<path d="'+line('q')+'" fill="none" stroke="#e9b75b" stroke-width="2"/>'+
    '<text x="30" y="255" fill="#cbd5e1" font-size="13">'+path[0].date+'</text>'+
    '<text x="770" y="255" fill="#cbd5e1" font-size="13">'+path.at(-1).date+'</text>';
}
function run(event) {
  event?.preventDefault();
  if (!source) return;
  try {
    const start=$('ndx86-start').value,end=$('ndx86-end').value;
    const initial=Number($('ndx86-initial').value),monthly=Number($('ndx86-monthly').value),
      drag=Number($('ndx86-drag').value)/100,costBps=Number($('ndx86-cost').value);
    if (start>end) throw Error('תאריך התחלה מאוחר מתאריך סיום');
    const rows=source.rows.filter(r=>r.date>=start&&r.date<=end&&r.l!==null);
    if (rows.length<2) throw Error('אין מספיק ימי מסחר לאחר תקופת חימום של 253 ימים');
    const result=simulateIndexResearch(rows,{initial,monthly,drag,costBps});
    $('ndx86-strategy').textContent=usd(result.strategy);
    $('ndx86-benchmark').textContent=usd(result.benchmark);
    $('ndx86-paid').textContent=usd(result.paid);
    $('ndx86-dd').textContent=pct(result.maxDD);
    draw(result.path);
    $('ndx86-status').textContent='נתוני מדד מ־'+source.period.source_start+' · סימולציה אפשרית מ־'+rows[0].date+
      ' עד '+rows.at(-1).date+' · '+rows.length.toLocaleString('en-US')+
      ' ימי מדד · חשיפה ממונפת סינתטית, לא ETF אמיתי · ללא חישוב מס.';
    $('ndx86-status').classList.remove('bad');
  } catch(e) {
    $('ndx86-status').textContent=e.message;
    $('ndx86-status').classList.add('bad');
  }
}
async function init() {
  const form=$('ndx86-form');
  if (!form) return;
  form.addEventListener('submit',run);
  try {
    const response=await fetch('ndx1986-research.json',{cache:'no-store'});
    if (!response.ok) throw Error('מקור נתוני 1986 עדיין לא פורסם');
    const data=await response.json();
    if (data.kind!=='STOCKLENS_NDX_1986_RETROACTIVE_INDEX_RESEARCH_V1'||
        data.status!=='RESEARCH_ONLY'||data.period?.source_start!=='1986-01-02'||
        !/^([a-f0-9]{64})$/.test(data.source?.download_sha256||'')||
        !Array.isArray(data.rows)||data.rows.length<9000||
        data.rows.at(-1).date!==data.period.source_end||
        data.rows.some((r,i)=>i>0&&r.date<=data.rows[i-1].date))
      throw Error('מקור נתוני המדד לא עבר בדיקת תקינות');
    source=data;
    $('ndx86-start').min=data.period.source_start;
    $('ndx86-start').max=data.period.source_end;
    $('ndx86-end').min=data.period.source_start;
    $('ndx86-end').max=data.period.source_end;
    $('ndx86-start').value=data.period.source_start;
    $('ndx86-end').value=data.period.source_end;
    run();
  } catch(e) {
    $('ndx86-status').textContent='מחקר 1986 חסום כרגע: '+e.message+'. הסימולטור הנצפה מ־2010 ממשיך לעבוד כרגיל.';
    $('ndx86-status').classList.add('bad');
  }
}
init();

export function sliceRange(rows,from,to){return rows.filter(r=>(!from||r.date>=from)&&(!to||r.date<=to))}
function metrics(rows){
 if(rows.length<2)return {sessions:rows.length,totalReturn:null,cagr:null,maxDrawdown:null,volatility:null,sharpeLike:null,turnover:null};
 let nav=1,peak=1,maxDD=0,rets=[],turnover=0,prevLev=rows[0].research_leverage??rows[0].frozen_leverage;
 for(let i=1;i<rows.length;i++){
  const q=rows[i].close/rows[i-1].close-1,lev=rows[i-1].research_leverage??rows[i-1].frozen_leverage,r=q*lev;
  nav*=1+r;peak=Math.max(peak,nav);maxDD=Math.min(maxDD,nav/peak-1);rets.push(r);turnover+=Math.abs(lev-prevLev);prevLev=lev;
 }
 const mean=rets.reduce((a,b)=>a+b,0)/rets.length,sd=Math.sqrt(rets.reduce((a,b)=>a+(b-mean)**2,0)/Math.max(1,rets.length-1));
 return {sessions:rows.length,totalReturn:nav-1,cagr:nav**(252/rets.length)-1,maxDrawdown:maxDD,volatility:sd*Math.sqrt(252),sharpeLike:sd?mean/sd*Math.sqrt(252):null,turnover};
}
export function simulate(rows,p){
 let prev=3,out=[],transitions=0,defenseDays=0;
 for(const r of rows){
  const trendOn=prev>1 ? r.close>=p.trendRetention*r.sma200 : r.close>p.trendReentry*r.sma200;let level;
  if(!trendOn)level=1;else if(prev===3)level=r.vol20>=p.l3ToL2?2:3;else if(prev===2)level=r.vol20>=p.l2ToL1?1:(r.vol20<p.l2ToL3?3:2);else level=r.vol20<p.l1ToL3?3:(r.vol20<p.l1ToL2?2:1);
  let defense=r.sma50<r.sma200&&r.mom12<=0;if(p.vixFilter&&r.vix!=null&&r.vix>=p.vixFilter)defense=true;
  const leverage=defense?0:({1:1.25,2:2,3:3}[level]);if(level!==prev)transitions++;if(defense)defenseDays++;
  out.push({...r,research_level:level,research_defense:defense,research_leverage:leverage});prev=level;
 }
 const baseline=out.map(r=>({...r,research_leverage:r.frozen_leverage}));
 return {rows:out,transitions,defenseDays,metrics:metrics(out),baselineMetrics:metrics(baseline)};
}

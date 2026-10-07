from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics
OUT=Path("research/gap15_regime_generalization_megabatch.json")
def build(out=OUT):
 rows,tq,_,_=_aligned();dates=pd.to_datetime([r["date"] for r in rows]);q=pd.Series([float(r["close"]) for r in rows],index=dates);qr=q.pct_change(fill_method=None)
 rv10=qr.rolling(10,10).std()*(252**.5);rv20=qr.rolling(20,20).std()*(252**.5);rv60=qr.rolling(60,40).std()*(252**.5);vcap=(.60/rv20.replace(0,float("nan"))).clip(1,3);acc=rv10>1.15*rv60;gap=qr.rolling(5,5).min()<-.05;tail=acc&gap;sma200=q.rolling(200,150).mean();trend=q/sma200-1
 def series(mode):
  ret=[];flags=[]
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]);cap=3.;j=i-1
   if mode!="baseline" and bool(acc.iloc[j]) and pd.notna(vcap.iloc[j]):cap=float(vcap.iloc[j])
   if mode=="gap15" and bool(tail.iloc[j]):cap=min(cap,1.5)
   e=min(frozen,cap);q0,t0=weights_for_leverage(e) if e>0 else (0.,0.);rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1;rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1;ret.append(TARGET_INVESTED_FRACTION*(q0*rq+t0*rt));flags.append(bool(tail.iloc[j]))
  return ret,flags
 base,_=series("baseline");gapret,hits=series("gap15")
 regimes={"low_rv20":rv20.shift(1).iloc[1:]<.20,"mid_rv20":(rv20.shift(1).iloc[1:]>=.20)&(rv20.shift(1).iloc[1:]<.35),"high_rv20":rv20.shift(1).iloc[1:]>=.35,"bull":trend.shift(1).iloc[1:]>=0,"bear":trend.shift(1).iloc[1:]<0}
 outreg={}
 for name,mask in regimes.items():
  ix=[i for i,v in enumerate(mask) if bool(v)];x=_path_metrics([gapret[i] for i in ix]);y=_path_metrics([base[i] for i in ix]);outreg[name]={"sessions":len(ix),"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"],"tail_hits":sum(hits[i] for i in ix)}
 years={}
 for yr in sorted(set(x.year for x in dates[1:])):
  ix=[i for i,x in enumerate(dates[1:]) if x.year==yr]
  if len(ix)<40:continue
  a=_path_metrics([gapret[i] for i in ix]);b=_path_metrics([base[i] for i in ix]);years[str(yr)]={"sessions":len(ix),"wealth_ratio":a["end_equity"]/b["end_equity"],"dd_improvement":a["max_drawdown"]-b["max_drawdown"],"tail_hits":sum(hits[i] for i in ix)}
 bad=[y for y,v in years.items() if v["wealth_ratio"]<.97 and v["dd_improvement"]<.01]
 res={"kind":"GAP15_REGIME_GENERALIZATION_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"regimes":outreg,"calendar_years":years,"adverse_years":bad,"decision_rule":{"no_threshold_retuning":True,"concern_if_multiple_adverse_years":True},"claim_boundary":"Generalization/falsification only; no automatic promotion."}
 Path(out).write_text(json.dumps(res,indent=2)+"\n");return res
if __name__=="__main__":print(json.dumps(build(),indent=2))

from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics
OUT=Path("research/execution_path_frontier_megabatch.json")
def build(out=OUT):
 rows,tq,_,_=_aligned();d=pd.to_datetime([r["date"] for r in rows]);q=pd.Series([float(r["close"]) for r in rows],index=d)
 def run(delay=0,cost=5.,turnover_band=0.,max_step=None):
  ret=[];lev=[];prev=0.
  for i in range(1,len(rows)):
   j=max(0,i-1-delay);target=float(rows[j]["leverage"]);e=target
   if turnover_band and abs(target-prev)<turnover_band:e=prev
   if max_step is not None:e=max(prev-max_step,min(prev+max_step,e))
   q0,t0=weights_for_leverage(e) if e>0 else (0.,0.);rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1;rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1;fee=cost/10000*abs(e-prev);ret.append(TARGET_INVESTED_FRACTION*(q0*rq+t0*rt)-fee);lev.append(e);prev=e
  return ret,lev
 base,_=run();bm=_path_metrics(base);cases={}
 specs={"delay1":(1,5.,0.,None),"delay2":(2,5.,0.,None),"cost10":(0,10.,0.,None),"cost25":(0,25.,0.,None),"band025":(0,5.,.25,None),"band050":(0,5.,.50,None),"step050":(0,5.,0.,.50),"step100":(0,5.,0.,1.),"delay1_cost10":(1,10.,0.,None),"delay2_cost10":(2,10.,0.,None)}
 for n,s in specs.items():
  r,l=run(*s);x=_path_metrics(r);cases[n]={"wealth_ratio":x["end_equity"]/bm["end_equity"],"dd_delta":x["max_drawdown"]-bm["max_drawdown"],"mean_leverage":sum(l)/len(l),"leverage_changes":sum(abs(l[i]-l[i-1])>1e-12 for i in range(1,len(l)))}
 # decade/path stability
 decades={}
 for start in (2010,2015,2020):
  ix=[i for i,x in enumerate(d[1:]) if start<=x.year<=min(start+4,d[-1].year)]
  if len(ix)<250:continue
  decades[str(start)]={}
  for n,s in {"base":(0,5.,0.,None),"delay1_cost10":(1,10.,0.,None),"band025":(0,5.,.25,None),"step100":(0,5.,0.,1.)}.items():
   r,_=run(*s);x=_path_metrics([r[i] for i in ix]);decades[str(start)][n]=x
 result={"kind":"EXECUTION_PATH_FRONTIER_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"promotion_allowed":False,"baseline":bm,"stress_cases":cases,"five_year_blocks":decades,"claim_boundary":"Execution/path robustness diagnostics only. Turnover bands and step limits are not optimized or eligible for promotion from this batch."}
 Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

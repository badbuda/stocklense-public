from __future__ import annotations
import json,random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics,_block_indices,_quantiles,BOOTSTRAPS,SEED
OUT=Path("research/accel10_tail_cap_ladder_megabatch.json")
CAPS=(2.5,2.25,2.0,1.75,1.5);BLOCKS=(5,21,63,126)
def build(out=OUT):
 rows,tq,_,_=_aligned();d=pd.to_datetime([r["date"] for r in rows]);q=pd.Series([float(r["close"]) for r in rows],index=d);qr=q.pct_change(fill_method=None)
 rv10=qr.rolling(10,10).std()*(252**.5);rv20=qr.rolling(20,20).std()*(252**.5);rv60=qr.rolling(60,40).std()*(252**.5);vcap=(.60/rv20.replace(0,float("nan"))).clip(1,3);acc=rv10>1.15*rv60
 gap=qr.rolling(5,5).min()<-.05;dd=q/q.cummax()-1;ddv=(dd-dd.shift(5))<-.06;sev=(rv10/rv60.replace(0,float("nan")))>1.5
 flags={"gap":acc&gap,"gap_ddv":acc&gap&ddv,"gap_sev":acc&gap&sev,"ddv_sev":acc&ddv&sev,"two_of_three":acc&((gap.astype(int)+ddv.astype(int)+sev.astype(int))>=2)}
 modes=["baseline","accel10"]+[f"{k}_cap{str(c).replace('.','')}" for k in flags for c in CAPS]
 def run(mode,lag=0,cost=0.):
  ret=[];lev=[];prev=None;hits=0
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]);j=i-1-lag;c=3.
   if j>=0 and mode!="baseline" and bool(acc.iloc[j]) and pd.notna(vcap.iloc[j]):c=float(vcap.iloc[j])
   if mode not in ("baseline","accel10") and j>=0:
    key,cs=mode.rsplit("_cap",1);tc=float(cs)/100 if len(cs)>2 else float(cs)/10
    if bool(flags[key].iloc[j]):c=min(c,tc)
   e=min(frozen,c);hits+=int(e<frozen-1e-12);q0,t0=weights_for_leverage(e) if e>0 else (0.,0.)
   rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1;rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
   fee=0 if prev is None else cost/10000.*abs(e-prev);prev=e;lev.append(e);ret.append(TARGET_INVESTED_FRACTION*(q0*rq+t0*rt)-fee)
  return ret,lev,hits
 series={};hist={}
 for m in modes:
  r,l,h=run(m);series[m]=r;x=_path_metrics(r);hist[m]={**x,"mean_leverage":sum(l)/len(l),"interventions":h}
 b=hist["baseline"]
 for m in modes[1:]:hist[m]["wealth_ratio"]=hist[m]["end_equity"]/b["end_equity"];hist[m]["dd_improvement"]=hist[m]["max_drawdown"]-b["max_drawdown"]
 # Pareto frontier, not winner selection
 candidates=[m for m in modes[2:]]
 pareto=[]
 for m in candidates:
  a=hist[m]
  dominated=any(hist[n]["wealth_ratio"]>=a["wealth_ratio"] and hist[n]["dd_improvement"]>=a["dd_improvement"] and (hist[n]["wealth_ratio"]>a["wealth_ratio"] or hist[n]["dd_improvement"]>a["dd_improvement"]) for n in candidates if n!=m)
  if not dominated:pareto.append(m)
 # Full lag and cost on every candidate; bootstrap only Pareto + accel10 to contain CI budget
 lag={};costs={}
 for m in modes[1:]:
  lag[m]={};costs[m]={}
  for L in (1,2,5):
   r,l,_=run(m,L);x=_path_metrics(r);lag[m][str(L)]={"wealth_ratio":x["end_equity"]/b["end_equity"],"dd_improvement":x["max_drawdown"]-b["max_drawdown"]}
  for cst in (2.5,5.,10.):
   r,l,_=run(m,0,cst);x=_path_metrics(r);costs[m][str(cst)]={"wealth_ratio":x["end_equity"]/b["end_equity"],"dd_improvement":x["max_drawdown"]-b["max_drawdown"]}
 boot={}
 for m in ["accel10"]+pareto:
  boot[m]={}
  for block in BLOCKS:
   rng=random.Random(SEED+block+sum(map(ord,m)));wr=[];di=[]
   for _ in range(BOOTSTRAPS):
    ix=_block_indices(len(series["baseline"]),block,rng);x=_path_metrics([series[m][i] for i in ix]);y=_path_metrics([series["baseline"][i] for i in ix]);wr.append(x["end_equity"]/y["end_equity"]);di.append(x["max_drawdown"]-y["max_drawdown"])
   boot[m][str(block)]={"wealth":_quantiles(wr),"dd":_quantiles(di),"p_preserve_85":sum(x>=.85 for x in wr)/len(wr),"p_dd_improve":sum(x>0 for x in di)/len(di)}
 res={"kind":"ACCEL10_TAIL_CAP_LADDER_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"design":{"base":"fixed accel10 RV10>1.15*RV60 with 60% RV20 cap","tail_caps":CAPS,"orthogonal_flags":list(flags),"selection":"coarse predeclared ladder; Pareto is descriptive only; no promotion"},"historical":hist,"pareto_frontier":pareto,"lag_falsification":lag,"cost_sensitivity":costs,"paired_cluster_bootstrap":boot,"claim_boundary":"Exploratory mechanism mapping; no threshold winner or frozen mutation."}
 Path(out).write_text(json.dumps(res,indent=2)+"\n");return res
if __name__=="__main__":print(json.dumps(build(),indent=2))

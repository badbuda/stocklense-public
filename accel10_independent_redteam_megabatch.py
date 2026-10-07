from __future__ import annotations
import json,random,math
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics,_block_indices,_quantiles,BOOTSTRAPS,SEED
OUT=Path("research/accel10_independent_redteam_megabatch.json");LAGS=(0,1,2,5);RELEASES=(1,3,5);BLOCKS=(5,21,63,126)
def build(out=OUT):
 rows,tq,_,_=_aligned();d=pd.to_datetime([r["date"] for r in rows]);q=pd.Series([float(r["close"]) for r in rows],index=d);qr=q.pct_change(fill_method=None)
 rv10=qr.rolling(10,10).std()*(252**.5);rv20=qr.rolling(20,20).std()*(252**.5);rv60=qr.rolling(60,40).std()*(252**.5);cap=(.60/rv20.replace(0,float("nan"))).clip(1,3)
 flags={"accel10":rv10>1.15*rv60,"accel20":rv20>1.15*rv60}
 def run(kind="baseline",lag=0,release=1,cost_bps=0.):
  ret=[];ex=[];hits=0;turn=0.;prev=None;held=3.;age=release
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]);j=i-1-lag;raw=3.
   if kind!="baseline" and j>=0 and bool(flags[kind].iloc[j]) and pd.notna(cap.iloc[j]):raw=float(cap.iloc[j])
   if release>1 and kind!="baseline":
    if raw<held:held=raw;age=0
    elif age<release:age+=1
    else:held=raw
    raw=held
   e=min(frozen,raw);hits+=int(e<frozen-1e-12)
   if prev is not None:turn+=abs(e-prev)
   prev=e;ex.append(e);q0,t0=weights_for_leverage(e) if e>0 else (0.,0.)
   rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1;rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
   gross=TARGET_INVESTED_FRACTION*(q0*rq+t0*rt);fee=(cost_bps/10000.)*(abs(e-ex[-2]) if len(ex)>1 else 0.)
   ret.append(gross-fee)
  return ret,ex,hits,turn
 base,_,_,_=run();bm=_path_metrics(base);variants={}
 for kind in ("accel10","accel20"):
  for lag in LAGS:
   for rel in RELEASES:
    k=f"{kind}_lag{lag}_release{rel}";r,e,h,t=run(kind,lag,rel);m=_path_metrics(r);sc=sum(e)/len(e)
    # matched static exposure
    sr=[] 
    for i in range(1,len(rows)):
     frozen=float(rows[i-1]["leverage"]);ee=min(frozen,sc);q0,t0=weights_for_leverage(ee) if ee>0 else (0.,0.);rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1;rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1;sr.append(TARGET_INVESTED_FRACTION*(q0*rq+t0*rt))
    sm=_path_metrics(sr);variants[k]={"wealth_ratio":m["end_equity"]/bm["end_equity"],"dd_improvement":m["max_drawdown"]-bm["max_drawdown"],"mean_leverage":sc,"interventions":h,"leverage_turnover":t,"matched_static_wealth_ratio":m["end_equity"]/sm["end_equity"],"matched_static_dd_improvement":m["max_drawdown"]-sm["max_drawdown"]}
 primary,_,_,_=run("accel10",0,1);sub={}
 for name,a,b in [("pre2020",None,"2019-12-31"),("post2020","2020-01-01",None),("covid","2020-02-01","2020-06-30"),("inflation2022","2022-01-01","2022-12-31")]:
  ix=[i for i,x in enumerate(d[1:]) if (a is None or x>=pd.Timestamp(a)) and (b is None or x<=pd.Timestamp(b))];x=_path_metrics([primary[i] for i in ix]);y=_path_metrics([base[i] for i in ix]);sub[name]={"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]}
 loco={}
 for name,a,b in [("covid","2020-02-01","2020-06-30"),("inflation2022","2022-01-01","2022-12-31")]:
  ix=[i for i,x in enumerate(d[1:]) if not(pd.Timestamp(a)<=x<=pd.Timestamp(b))];x=_path_metrics([primary[i] for i in ix]);y=_path_metrics([base[i] for i in ix]);loco[name]={"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]}
 boot={}
 for block in BLOCKS:
  rng=random.Random(SEED+31000+block);wr=[];di=[]
  for _ in range(BOOTSTRAPS):
   ix=_block_indices(len(base),block,rng);x=_path_metrics([primary[i] for i in ix]);y=_path_metrics([base[i] for i in ix]);wr.append(x["end_equity"]/y["end_equity"]);di.append(x["max_drawdown"]-y["max_drawdown"])
  boot[str(block)]={"wealth_ratio":_quantiles(wr),"dd_improvement":_quantiles(di),"p_preserve_85":sum(x>=.85 for x in wr)/len(wr),"p_dd_improve":sum(x>0 for x in di)/len(di)}
 costs={}
 for bps in (2.5,5.,10.,20.):
  r,_,_,t=run("accel10",0,1,bps);m=_path_metrics(r);costs[str(bps)]={"wealth_ratio":m["end_equity"]/bm["end_equity"],"dd_improvement":m["max_drawdown"]-bm["max_drawdown"],"leverage_turnover":t}
 result={"kind":"ACCEL10_INDEPENDENT_REDTEAM_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"selection_warning":"10d emerged from prior sensitivity; this batch is falsification only, not confirmation-by-retuning.","fixed_rules":{"accel10":"RV10 > 1.15*RV60","accel20_reference":"RV20 > 1.15*RV60","cap":"unchanged 60% target based on RV20"},"baseline":bm,"variants":variants,"subperiods":sub,"leave_one_crisis_out":loco,"paired_cluster_bootstrap":boot,"cost_sensitivity_bps_per_unit_leverage_turnover":costs,"claim_boundary":"Research-only; no promotion."}
 Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

from __future__ import annotations
import json,random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics,_block_indices,_quantiles,BOOTSTRAPS,SEED
OUT=Path("research/gap15_latency_redteam_megabatch.json");LAGS=(0,1,2,3,5);COSTS=(0.,2.5,5.,10.,20.);BLOCKS=(5,21,63,126)
def build(out=OUT):
 rows,tq,_,_=_aligned();dates=pd.to_datetime([r["date"] for r in rows]);q=pd.Series([float(r["close"]) for r in rows],index=dates);qr=q.pct_change(fill_method=None)
 rv10=qr.rolling(10,10).std()*(252**.5);rv20=qr.rolling(20,20).std()*(252**.5);rv60=qr.rolling(60,40).std()*(252**.5);vcap=(.60/rv20.replace(0,float("nan"))).clip(1,3);accel=rv10>1.15*rv60;gap=qr.rolling(5,5).min()<-.05;tail=accel&gap
 def run(mode="baseline",lag=0,cost=0.):
  ret=[];lev=[];prev=None;hits=0
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]);j=i-1-lag;cap=3.
   if mode!="baseline" and j>=0 and bool(accel.iloc[j]) and pd.notna(vcap.iloc[j]):cap=float(vcap.iloc[j])
   if mode=="gap15" and j>=0 and bool(tail.iloc[j]):cap=min(cap,1.5)
   e=min(frozen,cap);hits+=int(e<frozen-1e-12);q0,t0=weights_for_leverage(e) if e>0 else (0.,0.);rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1;rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1;fee=0. if prev is None else cost/10000.*abs(e-prev);prev=e;lev.append(e);ret.append(TARGET_INVESTED_FRACTION*(q0*rq+t0*rt)-fee)
  return ret,lev,hits
 series={m:run(m)[0] for m in ("baseline","accel10","gap15")};bm=_path_metrics(series["baseline"]);hist={}
 for m in series:
  r,l,h=run(m);x=_path_metrics(r);hist[m]={**x,"mean_leverage":sum(l)/len(l),"interventions":h,"wealth_ratio":x["end_equity"]/bm["end_equity"],"dd_improvement":x["max_drawdown"]-bm["max_drawdown"]}
 grid={}
 for m in ("accel10","gap15"):
  grid[m]={}
  for lag in LAGS:
   for cost in COSTS:
    r,_,_=run(m,lag,cost);x=_path_metrics(r);grid[m][f"lag{lag}_cost{cost:g}"]={"wealth_ratio":x["end_equity"]/bm["end_equity"],"dd_improvement":x["max_drawdown"]-bm["max_drawdown"]}
 periods={"pre2020":(None,"2019-12-31"),"post2020":("2020-01-01",None),"covid":("2020-02-01","2020-06-30"),"inflation2022":("2022-01-01","2022-12-31"),"post2022":("2023-01-01",None)};sub={}
 for name,(a,b) in periods.items():
  ix=[i for i,x in enumerate(dates[1:]) if (a is None or x>=pd.Timestamp(a)) and (b is None or x<=pd.Timestamp(b))];sub[name]={}
  for m in ("accel10","gap15"):
   x=_path_metrics([series[m][i] for i in ix]);y=_path_metrics([series["baseline"][i] for i in ix]);sub[name][m]={"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]}
 leave={}
 for name,(a,b) in {"covid":periods["covid"],"inflation2022":periods["inflation2022"]}.items():
  ix=[i for i,x in enumerate(dates[1:]) if not(pd.Timestamp(a)<=x<=pd.Timestamp(b))];leave[name]={}
  for m in ("accel10","gap15"):
   x=_path_metrics([series[m][i] for i in ix]);y=_path_metrics([series["baseline"][i] for i in ix]);leave[name][m]={"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]}
 boot={}
 for m in ("accel10","gap15"):
  boot[m]={}
  for block in BLOCKS:
   rng=random.Random(SEED+47000+block+sum(map(ord,m)));wr=[];di=[]
   for _ in range(BOOTSTRAPS):
    ix=_block_indices(len(series["baseline"]),block,rng);x=_path_metrics([series[m][i] for i in ix]);y=_path_metrics([series["baseline"][i] for i in ix]);wr.append(x["end_equity"]/y["end_equity"]);di.append(x["max_drawdown"]-y["max_drawdown"])
   boot[m][str(block)]={"wealth":_quantiles(wr),"dd":_quantiles(di),"p_preserve_90":sum(x>=.90 for x in wr)/len(wr),"p_dd_improve":sum(x>0 for x in di)/len(di)}
 res={"kind":"GAP15_LATENCY_REDTEAM_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"contract":{"candidate":"predeclared gap_cap15 from prior Pareto frontier","no_retuning":True,"promotion_allowed":False,"primary_falsification":"latency x cost grid plus subperiod, leave-crisis-out and paired cluster bootstrap"},"historical":hist,"latency_cost_grid":grid,"subperiods":sub,"leave_one_crisis_out":leave,"paired_cluster_bootstrap":boot,"continuation_rule":{"lag1_cost5_wealth_min":.90,"lag1_cost5_dd_improvement_min":.01,"bootstrap_p_dd_improve_min":.75},"claim_boundary":"Independent follow-up falsification of a previously declared Pareto candidate; no threshold search, no frozen mutation, no automatic promotion."}
 Path(out).write_text(json.dumps(res,indent=2)+"\n");return res
if __name__=="__main__":print(json.dumps(build(),indent=2))

from __future__ import annotations
import json, math, random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics,_block_indices,_quantiles,BOOTSTRAPS,SEED
OUT=Path("research/next_frontier_multidirection_megabatch.json")
def build(out=OUT):
 rows,tq,_,_=_aligned(); dates=pd.to_datetime([r["date"] for r in rows]); q=pd.Series([float(r["close"]) for r in rows],index=dates); r=q.pct_change(fill_method=None)
 rv10=r.rolling(10,10).std()*(252**.5);rv20=r.rolling(20,20).std()*(252**.5);rv60=r.rolling(60,40).std()*(252**.5)
 sma50=q.rolling(50,40).mean();sma200=q.rolling(200,150).mean();mom63=q/q.shift(63)-1;dd=q/q.cummax()-1
 breadth_proxy=(q>sma50)&(sma50>sma200); vcap=(.60/rv20.replace(0,float("nan"))).clip(1,3)
 # Coarse, predeclared mechanism families. Neighboring values are diagnostics, never winner selection.
 flags={
 "trend_quality":(q>sma200)&(sma50>sma200)&(mom63>0),
 "trend_break":(q<sma200)&(sma50<sma200),
 "vol_accel":rv10>1.15*rv60,
 "drawdown_state":dd<-.12,
 "recovery_state":(dd<-.05)&(mom63>0)&(q>sma50),
 "negative_cluster":(r<0).rolling(5,5).sum()>=4,
 "vol_of_vol":rv20.pct_change(5)>.25,
 "breadth_proxy":breadth_proxy,
 }
 def run(mode="baseline",cost=5.,lag=0):
  ret=[];lev=[];prev=None;hits=0
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]);j=i-1-lag;e=frozen
   if j>=0:
    if mode=="trend_break_cap2" and bool(flags["trend_break"].iloc[j]): e=min(e,2.)
    elif mode=="dd12_cap2" and bool(flags["drawdown_state"].iloc[j]): e=min(e,2.)
    elif mode=="negcluster_cap2" and bool(flags["negative_cluster"].iloc[j]): e=min(e,2.)
    elif mode=="vov_cap2" and bool(flags["vol_of_vol"].iloc[j]): e=min(e,2.)
    elif mode=="accel_vcap" and bool(flags["vol_accel"].iloc[j]) and pd.notna(vcap.iloc[j]): e=min(e,float(vcap.iloc[j]))
    elif mode=="quality_noadd" and not bool(flags["trend_quality"].iloc[j]): e=min(e,2.)
    elif mode=="recovery_cap25" and bool(flags["recovery_state"].iloc[j]): e=min(e,2.5)
   hits+=int(e<frozen-1e-12);q0,t0=weights_for_leverage(e) if e>0 else (0.,0.);rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1;rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
   fee=0 if prev is None else cost/10000*abs(e-prev);prev=e;ret.append(TARGET_INVESTED_FRACTION*(q0*rq+t0*rt)-fee);lev.append(e)
  return ret,lev,hits
 modes=("baseline","trend_break_cap2","dd12_cap2","negcluster_cap2","vov_cap2","accel_vcap","quality_noadd","recovery_cap25")
 series={};hist={}
 for m in modes:
  x,l,h=run(m);series[m]=x;z=_path_metrics(x);hist[m]={**z,"mean_leverage":sum(l)/len(l),"interventions":h}
 b=hist["baseline"];comparison={}
 for m in modes[1:]:
  x=hist[m];comparison[m]={"wealth_ratio":x["end_equity"]/b["end_equity"],"dd_improvement":x["max_drawdown"]-b["max_drawdown"]}
 # Generalization + execution stress only for coarse survivors; no threshold search.
 stress={}
 for m in modes[1:]:
  stress[m]={}
  for lag,cost in ((0,10.),(1,5.),(1,10.),(2,10.)):
   x,_,_=run(m,cost,lag);z=_path_metrics(x);stress[m][f"lag{lag}_cost{cost:g}"]={"wealth_ratio":z["end_equity"]/b["end_equity"],"dd_improvement":z["max_drawdown"]-b["max_drawdown"]}
 windows={}
 for m in modes[1:]:
  arr=[]
  for start in range(dates[1].year,dates[-1].year-1,3):
   a=pd.Timestamp(f"{start}-01-01");e=a+pd.DateOffset(years=3)-pd.Timedelta(days=1);ix=[i for i,d in enumerate(dates[1:]) if a<=d<=e]
   if len(ix)<500:continue
   x=_path_metrics([series[m][i] for i in ix]);y=_path_metrics([series["baseline"][i] for i in ix]);arr.append({"period":f"{start}-{start+2}","wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]})
  windows[m]=arr
 # Bootstrap only mechanisms that clear a deliberately broad continuation floor.
 survivors=[m for m in modes[1:] if comparison[m]["wealth_ratio"]>=.85 and comparison[m]["dd_improvement"]>=.015]
 boot={}
 for m in survivors:
  boot[m]={}
  for block in (21,63,126):
   rng=random.Random(SEED+99000+block+sum(map(ord,m)));wr=[];di=[]
   for _ in range(BOOTSTRAPS):
    ix=_block_indices(len(series["baseline"]),block,rng);x=_path_metrics([series[m][i] for i in ix]);y=_path_metrics([series["baseline"][i] for i in ix]);wr.append(x["end_equity"]/y["end_equity"]);di.append(x["max_drawdown"]-y["max_drawdown"])
   boot[m][str(block)]={"wealth":_quantiles(wr),"dd":_quantiles(di),"p_dd_improve":sum(v>0 for v in di)/len(di)}
 result={"kind":"NEXT_FRONTIER_MULTIDIRECTION_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"gap15_mutated":False,"promotion_allowed":False,
 "families":{"trend":["trend_break_cap2","quality_noadd"],"drawdown":["dd12_cap2","recovery_cap25"],"microstructure_proxy":["negcluster_cap2","vov_cap2"],"volatility":["accel_vcap"]},
 "contract":{"coarse_mechanisms_only":True,"no_neighbor_threshold_winner_selection":True,"survivor_floor":{"wealth_ratio":.85,"dd_improvement":.015},"survivor_requires_fresh_independent_redteam":True},
 "historical":hist,"comparison":comparison,"execution_stress":stress,"nonoverlap_3y":windows,"broad_survivors":survivors,"survivor_bootstrap":boot,
 "claim_boundary":"Discovery map only. A survivor is not a validated challenger and cannot be promoted; it requires a separately committed independent red-team."}
 Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

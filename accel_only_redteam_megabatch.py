from __future__ import annotations
import json, random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics, _block_indices, _quantiles, BOOTSTRAPS, SEED

OUT=Path("research/accel_only_redteam_megabatch.json")
LAGS=(0,1,2,5); RELEASES=(1,3,5); BLOCKS=(5,21,63)

def build(out=OUT):
 rows,tq,_,_=_aligned(); dates=pd.to_datetime([r["date"] for r in rows]); q=pd.Series([float(r["close"]) for r in rows],index=dates)
 qr=q.pct_change(fill_method=None); rv20=qr.rolling(20,min_periods=20).std()*(252**.5); rv60=qr.rolling(60,min_periods=40).std()*(252**.5)
 cap=(.60/rv20.replace(0,float("nan"))).clip(1,3); active=rv20>rv60*1.15
 def run(lag=0,release=1,static=None):
  ret=[]; ex=[]; hits=0; held=3.; age=release
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]); j=i-1-lag; raw=3.
   if static is not None: raw=float(static)
   elif j>=0 and bool(active.iloc[j]) and pd.notna(cap.iloc[j]): raw=float(cap.iloc[j])
   if release>1 and static is None:
    if raw<held: held=raw; age=0
    elif age<release: age+=1
    else: held=raw
    raw=held
   e=min(frozen,raw); ex.append(e); hits+=int(e<frozen-1e-12)
   q0,t0=weights_for_leverage(e) if e>0 else (0.,0.); rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1; rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
   ret.append(TARGET_INVESTED_FRACTION*(q0*rq+t0*rt))
  return ret,ex,hits
 base,_,_=run(static=3.); bm=_path_metrics(base); variants={}
 for lag in LAGS:
  for rel in RELEASES:
   k=f"lag{lag}_release{rel}"; r,e,h=run(lag,rel); m=_path_metrics(r); sc=sum(e)/len(e); sr,_,_=run(static=sc); sm=_path_metrics(sr)
   variants[k]={"full":m,"wealth_ratio":m["end_equity"]/bm["end_equity"],"dd_improvement":m["max_drawdown"]-bm["max_drawdown"],"mean_leverage":sc,"interventions":h,
    "matched_static":{"wealth_ratio":m["end_equity"]/sm["end_equity"],"dd_improvement":m["max_drawdown"]-sm["max_drawdown"]}}
 # subperiod and leave-crisis-out only for predeclared primary lag0/release1
 primary,_,_=run(0,1); periods={"pre2020":(None,"2019-12-31"),"post2020":("2020-01-01",None),"covid":("2020-02-01","2020-06-30"),"inflation2022":("2022-01-01","2022-12-31")}
 sub={}
 for name,(a,b) in periods.items():
  ix=[i for i,d in enumerate(dates[1:]) if (a is None or d>=pd.Timestamp(a)) and (b is None or d<=pd.Timestamp(b))]
  x=_path_metrics([primary[i] for i in ix]); y=_path_metrics([base[i] for i in ix]); sub[name]={"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]}
 loco={}
 for name,(a,b) in {"covid":("2020-02-01","2020-06-30"),"inflation2022":("2022-01-01","2022-12-31")}.items():
  ix=[i for i,d in enumerate(dates[1:]) if not(pd.Timestamp(a)<=d<=pd.Timestamp(b))]; x=_path_metrics([primary[i] for i in ix]); y=_path_metrics([base[i] for i in ix]); loco[name]={"wealth_ratio":x["end_equity"]/y["end_equity"],"dd_improvement":x["max_drawdown"]-y["max_drawdown"]}
 boot={}
 n=len(base)
 for block in BLOCKS:
  rng=random.Random(SEED+22000+block); wr=[]; dd=[]
  for _ in range(BOOTSTRAPS):
   ix=_block_indices(n,block,rng); x=_path_metrics([primary[i] for i in ix]); y=_path_metrics([base[i] for i in ix]); wr.append(x["end_equity"]/y["end_equity"]); dd.append(x["max_drawdown"]-y["max_drawdown"])
  boot[str(block)]={"wealth_ratio":_quantiles(wr),"dd_improvement":_quantiles(dd),"p_preserve_85":sum(x>=.85 for x in wr)/len(wr),"p_dd_improve":sum(x>0 for x in dd)/len(dd)}
 result={"kind":"ACCEL_ONLY_REDTEAM_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"fixed_definition":"RV20 > 1.15*RV60; when active apply unchanged 60% vol cap","no_optimizer":True,
  "baseline":bm,"variants":variants,"primary_subperiods":sub,"leave_one_crisis_out":loco,"paired_cluster_bootstrap":boot,
  "continuation_rule":"Primary must preserve >=85% wealth and improve MaxDD >=3pp; lag/matched/static/subperiod/bootstrap are falsification evidence, never auto-promotion.","claim_boundary":"Research-only; no promotion."}
 Path(out).write_text(json.dumps(result,indent=2)+"\n"); return result
if __name__=="__main__": print(json.dumps(build(),indent=2))

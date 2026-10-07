from __future__ import annotations
import json,random
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from orthogonal_tail_validation import _path_metrics,BLOCKS,BOOTSTRAPS,SEED,_block_indices,_quantiles
OUT=Path("research/acute_slow_layer_falsification.json")
LAGS=(0,1,2,5)
MODES=("baseline","acute","slow","layered")
EPISODES=(("2010_flash","2010-04-01","2010-10-31"),("2011_debt","2011-04-01","2011-12-31"),("2015_16","2015-04-01","2016-04-30"),("2018_q4","2018-08-01","2019-03-31"),("2020_covid","2020-01-01","2020-08-31"),("2022_bear","2021-10-01","2023-01-31"),("2024_window","2024-06-01","2024-12-31"))
# Predeclared existing mechanisms only:
# acute = existing 5-session term-severe pulse, cap2
# slow = existing trend200_negative20 OR existing market_credit_joint, cap2
def lag_features(f,n):
 if n<=0:return f
 o=f.copy()
 for c in ("term_severe_pulse5","trend200_negative20","market_credit_joint"):
  o[c]=o[c].shift(n).fillna(False).astype(bool)
 return o
def cap(f,dt,mode):
 if mode=="baseline" or dt not in f.index:return 3.
 acute=bool(f.at[dt,"term_severe_pulse5"])
 slow=bool(f.at[dt,"trend200_negative20"]) or bool(f.at[dt,"market_credit_joint"])
 hit=acute if mode=="acute" else slow if mode=="slow" else acute or slow
 return 2. if hit else 3.
def daily(rows,tq,f,mode):
 out=[];hits=0
 for i in range(1,len(rows)):
  frozen=float(rows[i-1]["leverage"]);c=cap(f,pd.Timestamp(rows[i-1]["date"]),mode);exp=min(frozen,c);hits+=int(exp<frozen-1e-12)
  q0,t0=weights_for_leverage(exp) if exp>0 else (0.,0.);q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
  out.append(q*(float(rows[i]["close"])/float(rows[i-1]["close"])-1.)+t*(tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1.))
 return out,hits
def episode(rows,rets,a,b):
 ds=[pd.Timestamp(r["date"]) for r in rows[1:]];idx=[i for i,d in enumerate(ds) if pd.Timestamp(a)<=d<=pd.Timestamp(b)]
 return _path_metrics([rets[i] for i in idx]) if idx else None
def paired(s):
 n=len(s["baseline"]);out={}
 for block in BLOCKS:
  rng=random.Random(SEED+7000+block);z={m:[] for m in MODES}
  for _ in range(BOOTSTRAPS):
   idx=_block_indices(n,block,rng)
   for m in MODES:z[m].append(_path_metrics([s[m][i] for i in idx]))
  b=z["baseline"];bo={}
  for m in MODES:
   v=z[m];dd=[x["max_drawdown"]-y["max_drawdown"] for x,y in zip(v,b)];wr=[x["end_equity"]/y["end_equity"] for x,y in zip(v,b)]
   bo[m]={"dd_improvement_vs_baseline":_quantiles(dd),"wealth_ratio_vs_baseline":_quantiles(wr),"p_dd_improve_vs_baseline":sum(x>0 for x in dd)/len(dd),"p_preserve_90pct_baseline_wealth":sum(x>=.9 for x in wr)/len(wr),"p_dd_ge_60pct":sum(x["max_drawdown"]<=-.6 for x in v)/len(v)}
  out[str(block)]=bo
 return out
def session_attribution(rows,s):
 out={}
 b=s["baseline"]
 for m in MODES[1:]:
  ds=[x-y for x,y in zip(s[m],b)];active=[i for i,x in enumerate(ds) if abs(x)>1e-15]
  pos=[i for i in active if b[i]>0];neg=[i for i in active if b[i]<0]
  out[m]={"changed_sessions":len(active),"positive_baseline_sessions_sacrificed":len(pos),"negative_baseline_sessions_cushioned":len(neg),"sum_return_delta":sum(ds),"positive_session_delta":sum(ds[i] for i in pos),"negative_session_delta":sum(ds[i] for i in neg)}
 return out
def build(out=OUT):
 rows,tq,_,_=_aligned();f=_augment(_download(rows[0]["date"],(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()));res={}
 for lag in LAGS:
  lf=lag_features(f,lag);s={};hits={}
  for m in MODES:s[m],hits[m]=daily(rows,tq,lf,m)
  b=_path_metrics(s["baseline"]);modes={}
  for m in MODES:
   x=_path_metrics(s[m]);modes[m]={"end_equity":x["end_equity"],"max_drawdown":x["max_drawdown"],"wealth_ratio_vs_baseline":x["end_equity"]/b["end_equity"],"maxdd_improvement_vs_baseline":x["max_drawdown"]-b["max_drawdown"],"intervention_sessions":hits[m]}
  eps={}
  for name,a,z in EPISODES:
   eb=episode(rows,s["baseline"],a,z)
   if eb is None:continue
   eps[name]={"baseline":eb}
   for m in MODES[1:]:
    x=episode(rows,s[m],a,z);eps[name][m]={"wealth_ratio_vs_baseline":x["end_equity"]/eb["end_equity"],"maxdd_improvement_vs_baseline":x["max_drawdown"]-eb["max_drawdown"],"max_drawdown":x["max_drawdown"]}
  res[str(lag)]={"modes":modes,"episodes":eps,"session_attribution":session_attribution(rows,s),"paired_cluster_bootstrap":paired(s)}
 r={"schema_version":1,"kind":"ACUTE_SLOW_LAYER_FALSIFICATION_RESEARCH_ONLY","frozen_model":"StockLens 8.0","frozen_model_mutated":False,"promotion_allowed":False,"lags_sessions":list(LAGS),"modes":list(MODES),"results":res,"mechanism_contract":{"acute":"existing term_severe_pulse5, cap2","slow":"existing trend200_negative20 OR existing market_credit_joint, cap2","layered":"union of acute and slow; cap2"},"anti_overfit_contract":["No new thresholds","No threshold search","Existing mechanisms only","Prior completed-session features","Lag grid fixed at 0/1/2/5","Paired block bootstrap uses identical sampled paths across mechanisms","Session attribution measures positive-session sacrifice versus negative-session cushioning","No promotion"],"claim_boundary":"Mechanism falsification only; historical episode behavior is not a forecast or production authorization."}
 Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

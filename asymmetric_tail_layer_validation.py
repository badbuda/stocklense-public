from __future__ import annotations
import json,random
from pathlib import Path
import pandas as pd
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from orthogonal_tail_validation import BLOCKS,BOOTSTRAPS,SEED,_block_indices,_path_metrics,_quantiles
OUT=Path("research/asymmetric_tail_layer_validation.json")
MODES=("baseline","pulse2","pulse125","fastshock2","pulse_fastshock2","pulse_fastshock125","pulse_slow2","pulse_fastshock_slow2")
LAGS=(0,1,2,5)
# Existing features/caps only. 1.25 severe cap and fast-shock/slow damage already existed in deep dive.
def _lag(f,n):
 if n<=0:return f
 o=f.copy()
 for c in ("term_severe_pulse5","fast_shock5d7_pulse5","trend200_negative20","market_credit_joint"):
  o[c]=o[c].shift(n).fillna(False).astype(bool)
 return o
def _cap(f,dt,m):
 if m=="baseline" or dt not in f.index:return 3.
 p=bool(f.at[dt,"term_severe_pulse5"]); sh=bool(f.at[dt,"fast_shock5d7_pulse5"]); slow=bool(f.at[dt,"trend200_negative20"]) or bool(f.at[dt,"market_credit_joint"])
 if m=="pulse2":return 2. if p else 3.
 if m=="pulse125":return 1.25 if p else 3.
 if m=="fastshock2":return 2. if sh else 3.
 if m=="pulse_fastshock2":return 2. if (p or sh) else 3.
 if m=="pulse_fastshock125":return 1.25 if (p and sh) else (2. if (p or sh) else 3.)
 if m=="pulse_slow2":return 2. if (p or slow) else 3.
 if m=="pulse_fastshock_slow2":return 2. if (p or sh or slow) else 3.
 raise ValueError(m)
def daily(rows,tq,f,m):
 out=[];hits=0
 for i in range(1,len(rows)):
  frozen=float(rows[i-1]["leverage"]);exp=min(frozen,_cap(f,pd.Timestamp(rows[i-1]["date"]),m));hits+=int(exp<frozen-1e-12)
  q0,t0=weights_for_leverage(exp) if exp>0 else (0.,0.);q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
  out.append(q*(float(rows[i]["close"])/float(rows[i-1]["close"])-1.)+t*(tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1.))
 return out,hits
def paired(s):
 n=len(s["baseline"]);out={}
 for block in BLOCKS:
  rng=random.Random(SEED+13000+block);z={m:[] for m in MODES}
  for _ in range(BOOTSTRAPS):
   idx=_block_indices(n,block,rng)
   for m in MODES:z[m].append(_path_metrics([s[m][i] for i in idx]))
  b=z["baseline"];bo={}
  for m in MODES:
   v=z[m];dd=[x["max_drawdown"]-y["max_drawdown"] for x,y in zip(v,b)];wr=[x["end_equity"]/y["end_equity"] for x,y in zip(v,b)]
   bo[m]={"dd_improvement":_quantiles(dd),"wealth_ratio":_quantiles(wr),"p_dd_improve":sum(x>0 for x in dd)/len(dd),"p_preserve_95pct_wealth":sum(x>=.95 for x in wr)/len(wr),"p_dd_ge_60pct":sum(x["max_drawdown"]<=-.6 for x in v)/len(v)}
  out[str(block)]=bo
 return out
def build(out=OUT):
 rows,tq,_,_=_aligned();f=_augment(_download(rows[0]["date"],(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()));res={}
 for lag in LAGS:
  lf=_lag(f,lag);s={};hits={}
  for m in MODES:s[m],hits[m]=daily(rows,tq,lf,m)
  b=_path_metrics(s["baseline"]);hist={}
  for m in MODES:
   x=_path_metrics(s[m]);hist[m]={"wealth_ratio":x["end_equity"]/b["end_equity"],"max_drawdown":x["max_drawdown"],"dd_improvement":x["max_drawdown"]-b["max_drawdown"],"intervention_sessions":hits[m]}
  res[str(lag)]={"historical":hist,"paired_cluster_bootstrap":paired(s)}
 r={"schema_version":1,"kind":"ASYMMETRIC_TAIL_LAYER_FALSIFICATION_RESEARCH_ONLY","frozen_model_mutated":False,"promotion_allowed":False,"modes":list(MODES),"lags_sessions":list(LAGS),"results":res,
 "contract":["No new signal thresholds","Existing term pulse, fast shock, slow damage and cap levels only","Conjunction pulse+fastshock uses existing signals and predeclared severe 1.25 cap","Prior completed-session features only","Paired identical bootstrap paths","Lag grid 0/1/2/5","No promotion"],
 "claim_boundary":"Tests whether sparse acute/severe layering can reduce tails more efficiently than broad continuous braking. Historical research only."}
 Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

from __future__ import annotations
import json,random
from pathlib import Path
import pandas as pd
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from orthogonal_tail_validation import BLOCKS,BOOTSTRAPS,SEED,_block_indices,_path_metrics,_quantiles
OUT=Path("research/state_aware_vol_brake_validation.json")
MODES=("baseline","vol_target","pulse_vol","vol_damage","pulse_vol_damage","vol_ensemble2","pulse_vol_ensemble2","vol_momentum","pulse_vol_momentum")
LAGS=(0,1,2,5)
# Frozen before outcome inspection. No new market thresholds:
# vol_target=.60/rv20 is existing; pulse5, trend200_negative20, market_credit_joint,
# momentum and ensemble2 are all existing declared features.
def _lag(f,n):
 if n<=0:return f
 o=f.copy()
 for c in ("rv20",):o[c]=o[c].shift(n)
 for c in ("term_severe_pulse5","trend200_negative20","market_credit_joint","momentum","ensemble2"):
  o[c]=o[c].shift(n).fillna(False).astype(bool)
 return o
def _cap(f,dt,m):
 if m=="baseline" or dt not in f.index:return 3.
 rv=float(f.at[dt,"rv20"]) if pd.notna(f.at[dt,"rv20"]) else 0.
 vol=max(1.,min(3.,.60/max(rv,.01)))
 pulse=bool(f.at[dt,"term_severe_pulse5"])
 damage=bool(f.at[dt,"trend200_negative20"]) or bool(f.at[dt,"market_credit_joint"])
 ens=bool(f.at[dt,"ensemble2"]); mom=bool(f.at[dt,"momentum"])
 if m=="vol_target":return vol
 if m=="pulse_vol":return min(vol,2. if pulse else 3.)
 if m=="vol_damage":return vol if damage else 3.
 if m=="pulse_vol_damage":return min(vol if damage else 3.,2. if pulse else 3.)
 if m=="vol_ensemble2":return vol if ens else 3.
 if m=="pulse_vol_ensemble2":return min(vol if ens else 3.,2. if pulse else 3.)
 if m=="vol_momentum":return vol if mom else 3.
 if m=="pulse_vol_momentum":return min(vol if mom else 3.,2. if pulse else 3.)
 raise ValueError(m)
def _daily(rows,tq,f,m):
 out=[];hits=0
 for i in range(1,len(rows)):
  frozen=float(rows[i-1]["leverage"]); exp=min(frozen,_cap(f,pd.Timestamp(rows[i-1]["date"]),m));hits+=int(exp<frozen-1e-12)
  q0,t0=weights_for_leverage(exp) if exp>0 else (0.,0.);q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
  out.append(q*(float(rows[i]["close"])/float(rows[i-1]["close"])-1.)+t*(tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1.))
 return out,hits
def _paired(s):
 n=len(s["baseline"]);out={}
 for block in BLOCKS:
  rng=random.Random(SEED+11000+block);z={m:[] for m in MODES}
  for _ in range(BOOTSTRAPS):
   idx=_block_indices(n,block,rng)
   for m in MODES:z[m].append(_path_metrics([s[m][i] for i in idx]))
  b=z["baseline"];bo={}
  for m in MODES:
   v=z[m];dd=[x["max_drawdown"]-y["max_drawdown"] for x,y in zip(v,b)];wr=[x["end_equity"]/y["end_equity"] for x,y in zip(v,b)]
   bo[m]={"dd_improvement":_quantiles(dd),"wealth_ratio":_quantiles(wr),"p_dd_improve":sum(x>0 for x in dd)/len(dd),"p_preserve_90pct_wealth":sum(x>=.9 for x in wr)/len(wr),"p_dd_ge_60pct":sum(x["max_drawdown"]<=-.6 for x in v)/len(v)}
  out[str(block)]=bo
 return out
def _attribution(s):
 b=s["baseline"];out={}
 for m in MODES[1:]:
  d=[x-y for x,y in zip(s[m],b)];active=[i for i,x in enumerate(d) if abs(x)>1e-15];pos=[i for i in active if b[i]>0];neg=[i for i in active if b[i]<0]
  out[m]={"changed_sessions":len(active),"positive_sessions_sacrificed":len(pos),"negative_sessions_cushioned":len(neg),"sum_delta":sum(d),"positive_delta":sum(d[i] for i in pos),"negative_delta":sum(d[i] for i in neg)}
 return out
def build(out=OUT):
 rows,tq,_,_=_aligned();f=_augment(_download(rows[0]["date"],(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()));res={}
 for lag in LAGS:
  lf=_lag(f,lag);s={};hits={}
  for m in MODES:s[m],hits[m]=_daily(rows,tq,lf,m)
  b=_path_metrics(s["baseline"]);hist={}
  for m in MODES:
   x=_path_metrics(s[m]); sacrifice=max(0.,1.-x["end_equity"]/b["end_equity"]); ddi=x["max_drawdown"]-b["max_drawdown"]
   hist[m]={"wealth_ratio":x["end_equity"]/b["end_equity"],"max_drawdown":x["max_drawdown"],"dd_improvement":ddi,"intervention_sessions":hits[m],"dd_improvement_per_10pct_wealth_sacrifice":(ddi/(sacrifice/.10) if sacrifice>1e-12 else None)}
  res[str(lag)]={"historical":hist,"session_attribution":_attribution(s),"paired_cluster_bootstrap":_paired(s)}
 r={"schema_version":1,"kind":"STATE_AWARE_VOL_BRAKE_FALSIFICATION_RESEARCH_ONLY","frozen_model_mutated":False,"promotion_allowed":False,"modes":list(MODES),"lags_sessions":list(LAGS),"results":res,
 "mechanism_contract":{"vol_target":"existing .60/rv20 continuous cap","acute":"existing term_severe_pulse5 cap2","damage":"existing trend200_negative20 OR market_credit_joint","ensemble2":"existing >=2/8 stress families","momentum":"existing declared momentum deterioration"},
 "anti_overfit_contract":["No new market thresholds","No threshold search","All gates existed before this comparison","Prior completed-session features only","Paired bootstrap paths identical across modes","Lag grid fixed 0/1/2/5","Efficiency metric is descriptive only","No automatic winner or promotion"],
 "claim_boundary":"Research falsification only. Same historical evidence used to compare pre-existing mechanisms; not pristine prospective validation or trading authorization."}
 Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

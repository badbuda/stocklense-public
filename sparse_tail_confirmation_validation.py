from __future__ import annotations
import json,random,math
from pathlib import Path
import pandas as pd
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from orthogonal_tail_validation import BLOCKS,BOOTSTRAPS,SEED,_block_indices,_path_metrics,_quantiles
OUT=Path("research/sparse_tail_confirmation_validation.json")
MODES=("baseline","pulse_slow2","pulse125_slow2","pulse_slow2_ensemble125","pulse125_slow2_ensemble125")
LAGS=(0,1,2,5)
# Second-stage confirmation keeps the already-declared sparse family intact.
def lagf(f,n):
 if n<=0:return f
 o=f.copy()
 for c in ("term_severe_pulse5","trend200_negative20","market_credit_joint","ensemble3"):
  o[c]=o[c].shift(n).fillna(False).astype(bool)
 return o
def cap(f,dt,m):
 if m=="baseline" or dt not in f.index:return 3.
 p=bool(f.at[dt,"term_severe_pulse5"]);slow=bool(f.at[dt,"trend200_negative20"]) or bool(f.at[dt,"market_credit_joint"]);e3=bool(f.at[dt,"ensemble3"])
 if m=="pulse_slow2":return 2. if (p or slow) else 3.
 if m=="pulse125_slow2":return 1.25 if p else (2. if slow else 3.)
 if m=="pulse_slow2_ensemble125":return 1.25 if e3 else (2. if (p or slow) else 3.)
 if m=="pulse125_slow2_ensemble125":return 1.25 if (p or e3) else (2. if slow else 3.)
 raise ValueError(m)
def daily(rows,tq,f,m):
 out=[];hits=0
 for i in range(1,len(rows)):
  fr=float(rows[i-1]["leverage"]);ex=min(fr,cap(f,pd.Timestamp(rows[i-1]["date"]),m));hits+=int(ex<fr-1e-12)
  q0,t0=weights_for_leverage(ex) if ex>0 else (0.,0.);q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
  out.append(q*(float(rows[i]["close"])/float(rows[i-1]["close"])-1)+t*(tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1))
 return out,hits
def paired(s):
 n=len(s["baseline"]);out={}
 for block in BLOCKS:
  rng=random.Random(SEED+15000+block);z={m:[] for m in MODES}
  for _ in range(BOOTSTRAPS):
   idx=_block_indices(n,block,rng)
   for m in MODES:z[m].append(_path_metrics([s[m][i] for i in idx]))
  b=z["baseline"];bo={}
  for m in MODES:
   v=z[m];dd=[x["max_drawdown"]-y["max_drawdown"] for x,y in zip(v,b)];wr=[x["end_equity"]/y["end_equity"] for x,y in zip(v,b)]
   bo[m]={"dd_improvement":_quantiles(dd),"wealth_ratio":_quantiles(wr),"p_dd_improve":sum(x>0 for x in dd)/len(dd),"p_preserve_95pct_wealth":sum(x>=.95 for x in wr)/len(wr),"p_dd_ge_60pct":sum(x["max_drawdown"]<=-.6 for x in v)/len(v)}
  out[str(block)]=bo
 return out

# Large-batch screen motivated by the independent leverage review. It deliberately
# reuses one data load and one CI run. This is exploratory/falsification evidence,
# not a promotion search. Coarse grids are declared here before outcome inspection.
STATIC_CAPS=(1.0,1.25,1.5,1.75,2.0,2.25,2.5,2.75,3.0)
VOL_TARGETS=(0.25,0.30,0.35)
MEGA_LAGS=(0,1,2,5)
def _market_features(rows):
 idx=pd.to_datetime([r["date"] for r in rows]); px=pd.Series([float(r["close"]) for r in rows],index=idx)
 ret=px.pct_change()
 return pd.DataFrame({"rv20":ret.rolling(20).std()*math.sqrt(252),"rv63":ret.rolling(63).std()*math.sqrt(252),
  "sma200":px.rolling(200).mean(),"close":px})
def _mega_cap(name,dt,mf,f):
 if name.startswith("static_"):return float(name.split("_")[1])
 if dt not in mf.index:return 3.
 rv=max(float(mf.at[dt,"rv20"]),float(mf.at[dt,"rv63"])) if pd.notna(mf.at[dt,"rv63"]) else float("nan")
 if name.startswith("vol1_"):
  target=float(name.split("_")[1]);return min(3.,target/rv) if rv>0 else 3.
 if name.startswith("vol2_"):
  target=float(name.split("_")[1]);return min(3.,(target/rv)**2) if rv>0 else 3.
 if name=="trend_cap2":
  return 2. if pd.notna(mf.at[dt,"sma200"]) and float(mf.at[dt,"close"])<float(mf.at[dt,"sma200"]) else 3.
 if name.startswith("voltrend_"):
  target=float(name.split("_")[1]);v=min(3.,target/rv) if rv>0 else 3.
  return min(v,2.) if pd.notna(mf.at[dt,"sma200"]) and float(mf.at[dt,"close"])<float(mf.at[dt,"sma200"]) else v
 if name=="sparse_champion":
  return cap(f,dt,"pulse125_slow2_ensemble125")
 if name.startswith("sparse_vol_"):
  target=float(name.split("_")[2]);v=min(3.,target/rv) if rv>0 else 3.
  return min(v,cap(f,dt,"pulse125_slow2_ensemble125"))
 raise ValueError(name)
def _mega_path(rows,tq,mf,f,name,lag):
 rr=[];exps=[];hits=0
 for i in range(1,len(rows)):
  src=i-1; sig=max(0,src-lag);dt=pd.Timestamp(rows[sig]["date"])
  fr=float(rows[src]["leverage"]);ex=min(fr,_mega_cap(name,dt,mf,f));hits+=int(ex<fr-1e-12);exps.append(ex)
  q0,t0=weights_for_leverage(ex) if ex>0 else (0.,0.);q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
  rr.append(q*(float(rows[i]["close"])/float(rows[src]["close"])-1)+t*(tq[rows[i]["date"]]/tq[rows[src]["date"]]-1))
 x=_path_metrics(rr);return rr,{"end_equity":x["end_equity"],"max_drawdown":x["max_drawdown"],"avg_exposure":sum(exps)/len(exps),"intervention_sessions":hits}
def mega_screen(rows,tq,f):
 mf=_market_features(rows)
 names=[f"static_{x}" for x in STATIC_CAPS]
 names+=["trend_cap2"]
 for x in VOL_TARGETS:names += [f"vol1_{x}",f"vol2_{x}",f"voltrend_{x}",f"sparse_vol_{x}"]
 names+=["sparse_champion"]
 out={}
 for lag in MEGA_LAGS:
  paths={};stats={}
  for n in names:paths[n],stats[n]=_mega_path(rows,tq,mf,f,n,lag)
  base_rr,_=_mega_path(rows,tq,mf,f,"static_3.0",lag);base=_path_metrics(base_rr)
  for n in names:
   stats[n]["wealth_ratio_vs_uncapped"]=stats[n]["end_equity"]/base["end_equity"]
   stats[n]["dd_improvement_vs_uncapped"]=stats[n]["max_drawdown"]-base["max_drawdown"]
   if not n.startswith("static_"):
    nearest=min((s for s in names if s.startswith("static_")),key=lambda s:abs(stats[s]["avg_exposure"]-stats[n]["avg_exposure"]))
    stats[n]["matched_static"]=nearest
    stats[n]["wealth_ratio_vs_matched_static"]=stats[n]["end_equity"]/stats[nearest]["end_equity"]
    stats[n]["dd_improvement_vs_matched_static"]=stats[n]["max_drawdown"]-stats[nearest]["max_drawdown"]
  out[str(lag)]=stats
 return {"coarse_predeclared_grid":{"static_caps":STATIC_CAPS,"vol_targets":VOL_TARGETS,"lags":MEGA_LAGS},
  "results":out,"interpretation_rule":"A dynamic candidate must beat the matched-average-exposure static null frontier; otherwise apparent protection is just less leverage.",
  "claim_boundary":"Exploratory large-batch screen only. No parameter is promoted from this output; finalists require independent robustness and prospective evidence."}

def build(out=OUT):
 rows,tq,_,_=_aligned();f=_augment(_download(rows[0]["date"],(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()));res={}
 for lag in LAGS:
  lf=lagf(f,lag);s={};hits={}
  for m in MODES:s[m],hits[m]=daily(rows,tq,lf,m)
  b=_path_metrics(s["baseline"]);hist={}
  for m in MODES:
   x=_path_metrics(s[m]);hist[m]={"wealth_ratio":x["end_equity"]/b["end_equity"],"max_drawdown":x["max_drawdown"],"dd_improvement":x["max_drawdown"]-b["max_drawdown"],"intervention_sessions":hits[m]}
  res[str(lag)]={"historical":hist,"paired_cluster_bootstrap":paired(s)}
 r={"schema_version":2,"kind":"SPARSE_TAIL_CONFIRMATION_AND_DRAWDOWN_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,"promotion_allowed":False,"modes":list(MODES),"lags_sessions":list(LAGS),"results":res,
 "drawdown_megabatch":mega_screen(rows,tq,f),
 "contract":["Sparse confirmation family unchanged","Mega-batch adds static null frontier, 1/sigma, 1/sigma^2, trend gate, sparse+vol combinations","Coarse parameter grids declared in source before outcome inspection","Prior completed-session features only","Lag 0/1/2/5","Matched-average-exposure static comparison required","No promotion"],
 "claim_boundary":"Historical research only. Sparse confirmation remains non-independent; mega-batch is exploratory. Prospective evidence required before any promotion."}
 Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

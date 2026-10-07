from __future__ import annotations
import json,random
from pathlib import Path
import pandas as pd
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from orthogonal_tail_validation import BLOCKS,BOOTSTRAPS,SEED,_block_indices,_path_metrics,_quantiles
OUT=Path("research/vol_gate_existing_variants_validation.json")
MODES=("baseline","vol_target","vol_high_only","vol_tiers_light","pulse_vol","pulse_vol_high_only","pulse_vol_tiers_light","selective_high25","selective_high30","selective_high35","selective_high40","pulse2_fast","pulse2_rv25","pulse225_rv25","pulse25_rv25","shock2_rv25","drawdown2_rv25","trend2_rv25","joint2_rv25","momentum2_rv25","pulse3_cap2","pulse3_cap225","pulse3_cap25","pulse5_cap225","pulse5_cap25","pulse10_cap2","shock5_cap2","qdd10_cap2","term_persist_cap2","term_recovery_cap2","term_now_cap25","term_now_cap225","term_severe_now_cap25","term_cross_cap25","term_or_cross_cap25","term_vvix_cap25","term_participation_cap25","credit_term_cap25","breadth_term_cap25","term_severe_now_cap275","term_severe_pulse3_cap275","term_severe_pulse5_cap275","term_severe_pulse10_cap275")
LAGS=(0,1,2,5)
def _lag(f,n):
 if n<=0:return f
 o=f.copy();
 for col in ("rv20","term","term_severe","term_cross_confirmed","term_or_cross","term_or_vvix","term_or_participation","credit_term","breadth_term","term_severe_pulse3","term_severe_pulse5","term_severe_pulse10","fast_shock5d7_pulse5","qqq_drawdown10","term_persist2","term_severe_recovery3","pulse5_or_drawdown10","trend200_negative20","market_credit_joint","momentum_break"):
  if col in o.columns:o[col]=o[col].shift(n)
 for col in ("term","term_severe","term_cross_confirmed","term_or_cross","term_or_vvix","term_or_participation","credit_term","breadth_term","term_severe_pulse3","term_severe_pulse5","term_severe_pulse10","fast_shock5d7_pulse5","qqq_drawdown10","term_persist2","term_severe_recovery3","pulse5_or_drawdown10","trend200_negative20","market_credit_joint","momentum_break"):
  if col in o.columns:o[col]=o[col].fillna(False).astype(bool)
 return o
def _cap(f,dt,m):
 if m=="baseline" or dt not in f.index:return 3.
 rv=float(f.at[dt,"rv20"]) if pd.notna(f.at[dt,"rv20"]) else 0.;pulse=bool(f.at[dt,"term_severe_pulse5"])
 vt=max(1.,min(3.,.60/max(rv,.01)));vh=max(1.25,min(3.,.75/max(rv,.01))) if rv>=.25 else 3.;vl=1.75 if rv>=.40 else (2.25 if rv>=.30 else (2.75 if rv>=.25 else 3.)); selective={"selective_high25":2.5 if rv>=.25 else 3.,"selective_high30":2.5 if rv>=.30 else 3.,"selective_high35":2.5 if rv>=.35 else 3.,"selective_high40":2.5 if rv>=.40 else 3.}
 if m in selective:return selective[m]
 event_modes={
  "pulse2_fast":(pulse,2.0),
  "pulse2_rv25":(pulse and rv>=.25,2.0),
  "pulse225_rv25":(pulse and rv>=.25,2.25),
  "pulse25_rv25":(pulse and rv>=.25,2.5),
  "shock2_rv25":(bool(f.at[dt,"fast_shock5d7_pulse5"]) and rv>=.25,2.0),
  "drawdown2_rv25":(bool(f.at[dt,"pulse5_or_drawdown10"]) and rv>=.25,2.0),
  "trend2_rv25":(bool(f.at[dt,"trend200_negative20"]) and rv>=.25,2.0),
  "joint2_rv25":(bool(f.at[dt,"market_credit_joint"]) and rv>=.25,2.0),
  "momentum2_rv25":(bool(f.at[dt,"momentum_break"]) and rv>=.25,2.0),
  "pulse3_cap2":(bool(f.at[dt,"term_severe_pulse3"]),2.0),
  "pulse3_cap225":(bool(f.at[dt,"term_severe_pulse3"]),2.25),
  "pulse3_cap25":(bool(f.at[dt,"term_severe_pulse3"]),2.5),
  "pulse5_cap225":(pulse,2.25),
  "pulse5_cap25":(pulse,2.5),
  "pulse10_cap2":(bool(f.at[dt,"term_severe_pulse10"]),2.0),
  "shock5_cap2":(bool(f.at[dt,"fast_shock5d7_pulse5"]),2.0),
  "qdd10_cap2":(bool(f.at[dt,"qqq_drawdown10"]),2.0),
  "term_persist_cap2":(bool(f.at[dt,"term_persist2"]),2.0),
  "term_recovery_cap2":(bool(f.at[dt,"term_severe_recovery3"]),2.0),
  "term_severe_now_cap275":(bool(f.at[dt,"term_severe"]),2.75),
  "term_severe_pulse3_cap275":(bool(f.at[dt,"term_severe_pulse3"]),2.75),
  "term_severe_pulse5_cap275":(pulse,2.75),
  "term_severe_pulse10_cap275":(bool(f.at[dt,"term_severe_pulse10"]),2.75),
  "term_now_cap25":(bool(f.at[dt,"term"]),2.5),
  "term_now_cap225":(bool(f.at[dt,"term"]),2.25),
  "term_severe_now_cap25":(bool(f.at[dt,"term_severe"]),2.5),
  "term_cross_cap25":(bool(f.at[dt,"term_cross_confirmed"]),2.5),
  "term_or_cross_cap25":(bool(f.at[dt,"term_or_cross"]),2.5),
  "term_vvix_cap25":(bool(f.at[dt,"term_or_vvix"]),2.5),
  "term_participation_cap25":(bool(f.at[dt,"term_or_participation"]),2.5),
  "credit_term_cap25":(bool(f.at[dt,"credit_term"]),2.5),
  "breadth_term_cap25":(bool(f.at[dt,"breadth_term"]),2.5)}
 if m in event_modes:
  hit,cap=event_modes[m];return cap if hit else 3.
 base=vt if m in ("vol_target","pulse_vol") else vh if m in ("vol_high_only","pulse_vol_high_only") else vl
 return min(base,2. if pulse else 3.) if m.startswith("pulse_") else base
def _daily(rows,tq,f,m):
 out=[];hits=0
 for i in range(1,len(rows)):
  frozen=float(rows[i-1]["leverage"]);exp=min(frozen,_cap(f,pd.Timestamp(rows[i-1]["date"]),m));hits+=int(exp<frozen-1e-12)
  q0,t0=weights_for_leverage(exp) if exp>0 else (0.,0.);q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
  out.append(q*(float(rows[i]["close"])/float(rows[i-1]["close"])-1)+t*(tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1))
 return out,hits
def _paired(s):
 n=len(s["baseline"]);out={}
 for block in BLOCKS:
  rng=random.Random(SEED+9000+block);z={m:[] for m in MODES}
  for _ in range(BOOTSTRAPS):
   idx=_block_indices(n,block,rng)
   for m in MODES:z[m].append(_path_metrics([s[m][i] for i in idx]))
  b=z["baseline"];bo={}
  for m in MODES:
   v=z[m];dd=[x["max_drawdown"]-y["max_drawdown"] for x,y in zip(v,b)];wr=[x["end_equity"]/y["end_equity"] for x,y in zip(v,b)]
   bo[m]={"dd_improvement":_quantiles(dd),"wealth_ratio":_quantiles(wr),"p_dd_improve":sum(x>0 for x in dd)/len(dd),"p_preserve_90pct_wealth":sum(x>=.9 for x in wr)/len(wr),"p_dd_ge_60pct":sum(x["max_drawdown"]<=-.6 for x in v)/len(v)}
  out[str(block)]=bo
 return out
def build(out=OUT):
 rows,tq,_,_=_aligned();f=_augment(_download(rows[0]["date"],(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()));res={}
 for lag in LAGS:
  lf=_lag(f,lag);s={};hits={}
  for m in MODES:s[m],hits[m]=_daily(rows,tq,lf,m)
  b=_path_metrics(s["baseline"]);hist={}
  for m in MODES:
   x=_path_metrics(s[m]);hist[m]={"wealth_ratio":x["end_equity"]/b["end_equity"],"max_drawdown":x["max_drawdown"],"dd_improvement":x["max_drawdown"]-b["max_drawdown"],"intervention_sessions":hits[m]}
  res[str(lag)]={"historical":hist,"paired_cluster_bootstrap":_paired(s)}
 r={"schema_version":1,"kind":"EXISTING_VOL_GATE_VARIANTS_FALSIFICATION_RESEARCH_ONLY","frozen_model_mutated":False,"promotion_allowed":False,"modes":list(MODES),"lags_sessions":list(LAGS),"results":res,"contract":["All mechanisms and thresholds already existed in risk_overlay_deep_dive before this comparison","Selective RV thresholds 25/30/35/40% are a coarse predeclared stress grid, not optimized after outcome inspection","Identical paired bootstrap paths","Lag grid fixed at 0/1/2/5","Event-confirmed batch uses only pre-existing binary stress features plus RV25 confirmation; cap grid 2.0/2.25/2.5 is coarse and predeclared","Timing mega-batch adds pre-existing pulse durations 3/5/10, shock, drawdown, persistence and recovery-state variants; no outcome-derived threshold","Early-warning mega-batch tests same-session pre-existing term/cross/VVIX/participation/credit/breadth signals at moderate caps; all still execute only on the next return after a completed signal session","Lag-resilience severity check uses a single lighter 2.75x cap across severe-now and pulse3/5/10 durations; this is a coarse mechanism check, not optimization","No automatic winner selection or promotion","Selective candidate continuation gate: lag0 and lag1 must each preserve >=90% historical wealth and improve historical MaxDD >=1pp; paired bootstrap median wealth >=90% and p_dd_improve >=0.60"],"claim_boundary":"Comparative falsification of already-predeclared mechanisms; not a forecast or production authorization."}
 Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

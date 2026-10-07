from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from pulse_vol_component_attribution import cap
OUT=Path("research/vol_brake_rebound_attribution.json"); H=(1,5,10,21,63)
def q(a,p):
 if not a:return None
 s=sorted(a); return float(s[round((len(s)-1)*p)])
def build(out=OUT):
 rows,tq,_,_=_aligned();f=_augment(_download(rows[0]["date"],(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()))
 px=[float(r["close"]) for r in rows]; hits=[]
 for i in range(1,len(rows)-max(H)):
  frozen=float(rows[i-1]["leverage"]);dt=pd.Timestamp(rows[i-1]["date"]);vc=cap(f,dt,"vol_only")
  if min(frozen,vc)>=frozen-1e-12:continue
  rec={"date":str(dt.date()),"frozen_leverage":frozen,"vol_cap":vc}
  for h in H:rec[f"qqq_fwd_{h}d"]=px[i-1+h]/px[i-1]-1.
  hits.append(rec)
 res={}
 for h in H:
  vals=[x[f"qqq_fwd_{h}d"] for x in hits]
  res[str(h)]={"sessions":len(vals),"positive_fraction":sum(x>0 for x in vals)/len(vals),"negative_fraction":sum(x<0 for x in vals)/len(vals),
   "median":q(vals,.5),"p10":q(vals,.1),"p90":q(vals,.9),"mean":sum(vals)/len(vals)}
 # Fixed, descriptive regime labels: no thresholds are used to alter exposure or select a strategy.
 # Attribute intervention opportunity cost using only already-defined observable states.
 states={"pulse_overlap":[],"trend_damage":[],"drawdown10":[],"recovery_state":[],"other":[]}
 for x in hits:
  dt=pd.Timestamp(x["date"])
  if bool(f.at[dt,"term_severe_pulse5"]): k="pulse_overlap"
  elif bool(f.at[dt,"trend200_negative20"]): k="trend_damage"
  elif bool(f.at[dt,"qqq_drawdown10"]): k="drawdown10"
  elif bool(f.at[dt,"term_severe_recovery3"]): k="recovery_state"
  else:k="other"
  states[k].append(x)
 state_summary={k:{"sessions":len(v),"fraction":len(v)/len(hits) if hits else 0.,"positive_1d_fraction":sum(x["qqq_fwd_1d"]>0 for x in v)/len(v) if v else None,"median_21d":q([x["qqq_fwd_21d"] for x in v],.5),"median_63d":q([x["qqq_fwd_63d"] for x in v],.5)} for k,v in states.items()}
 buckets={"continued_loss_21d":[x for x in hits if x["qqq_fwd_21d"]<0],"rebound_21d":[x for x in hits if x["qqq_fwd_21d"]>0]}
 r={"schema_version":1,"kind":"VOL_BRAKE_REBOUND_ATTRIBUTION_RESEARCH_ONLY","frozen_model_mutated":False,"promotion_allowed":False,"horizons_sessions":list(H),"vol_intervention_sessions":len(hits),"forward_qqq_after_vol_brake":res,
 "observable_state_attribution":state_summary,"descriptive_21d_regimes":{k:{"sessions":len(v),"fraction":len(v)/len(hits),"median_21d":q([x["qqq_fwd_21d"] for x in v],.5),"median_63d":q([x["qqq_fwd_63d"] for x in v],.5)} for k,v in buckets.items()},
 "anti_overfit_contract":["Existing vol_target intervention definition only","Horizons fixed at 1/5/10/21/63 sessions","Forward returns are diagnostic labels only and never available to the strategy","Observable state buckets use existing pulse/trend/drawdown/recovery definitions only","No threshold search","No promotion"],
 "claim_boundary":"Ex-post attribution only. Forward outcomes diagnose opportunity cost/protection and cannot be used as causal real-time signals."}
 Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

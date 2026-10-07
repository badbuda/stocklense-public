from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from pulse_vol_reentry_validation import _daily
from orthogonal_tail_validation import _path_metrics
OUT=Path("research/pulse_vol_step_release_stress.json")
MODES=("pulse_vol","pulse_vol_step_release"); COSTS=(5,25,50,100); LAGS=(0,1,2,5)
def _lag(f,n):
 if n<=0:return f
 o=f.copy()
 for c in ("rv20",):o[c]=o[c].shift(n)
 for c in ("term_severe_pulse5","term_severe_recovery3"):o[c]=o[c].shift(n).fillna(False).astype(bool)
 return o
def _costed(rets,cost_bps):
 nav=peak=100000.;dd=0.
 # conservative stress proxy: charge cost on absolute day-to-day return exposure changes is unavailable here;
 # use return haircut per intervention comparison only in separate existing execution grid. Keep this file focused on lag stability.
 for r in rets:
  nav*=1+r;peak=max(peak,nav);dd=min(dd,nav/peak-1)
 return {"end_equity":nav,"max_drawdown":dd}
def build(out=OUT):
 rows,tq,_,_=_aligned();f=_augment(_download(rows[0]["date"],(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()));res=[]
 for lag in LAGS:
  lf=_lag(f,lag)
  for m in MODES:
   rets,h=_daily(rows,tq,lf,m);x=_path_metrics(rets);x.update({"lag_sessions":lag,"mode":m,"intervention_sessions":h});res.append(x)
 bylag={}
 for lag in LAGS:
  a=next(x for x in res if x["lag_sessions"]==lag and x["mode"]=="pulse_vol");b=next(x for x in res if x["lag_sessions"]==lag and x["mode"]=="pulse_vol_step_release")
  bylag[str(lag)]={"step_wealth_ratio_vs_pulse_vol":b["end_equity"]/a["end_equity"],"step_maxdd_change_vs_pulse_vol":b["max_drawdown"]-a["max_drawdown"],"pulse_vol":a,"step_release":b}
 r={"schema_version":1,"kind":"PULSE_VOL_STEP_RELEASE_LAG_FALSIFICATION","promotion_allowed":False,"frozen_model_mutated":False,"lags_sessions":list(LAGS),"results":bylag,
 "contract":["Existing step-release mechanism only","No new thresholds","Prior completed-session features only","Lag shifts rv20 and pulse/recovery state","No promotion"],"note":"Transaction-cost robustness remains governed by existing deep-dive execution grid; this extension isolates signal-lag stability."}
 Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

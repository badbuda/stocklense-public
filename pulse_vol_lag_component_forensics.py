from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from tqqq_reality_check import _aligned
from risk_overlay_multifactor import _download
from risk_overlay_deep_dive import _augment
from pulse_vol_component_attribution import daily as _daily
from orthogonal_tail_validation import _path_metrics
OUT=Path("research/pulse_vol_lag_component_forensics.json")
MODES=("baseline","pulse_only","vol_only","pulse_vol"); LAGS=(0,1,2,5)
EPISODES=(("2010_flash","2010-04-01","2010-10-31"),("2011_debt","2011-04-01","2011-12-31"),("2015_16","2015-04-01","2016-04-30"),("2018_q4","2018-08-01","2019-03-31"),("2020_covid","2020-01-01","2020-08-31"),("2022_bear","2021-10-01","2023-01-31"),("2024_window","2024-06-01","2024-12-31"))
def lag_features(f,n):
 if n<=0:return f
 o=f.copy();o["rv20"]=o["rv20"].shift(n);o["term_severe_pulse5"]=o["term_severe_pulse5"].shift(n).fillna(False).astype(bool);return o
def episode(rows,rets,start,end):
 ds=[pd.Timestamp(r["date"]) for r in rows[1:]];idx=[i for i,d in enumerate(ds) if pd.Timestamp(start)<=d<=pd.Timestamp(end)]
 if not idx:return None
 x=[rets[i] for i in idx];return _path_metrics(x)
def build(out=OUT):
 rows,tq,_,_=_aligned();f=_augment(_download(rows[0]["date"],(pd.Timestamp(rows[-1]["date"])+pd.Timedelta(days=2)).date().isoformat()));allres={}
 for lag in LAGS:
  lf=lag_features(f,lag);series={};hits={}
  for m in MODES:series[m],hits[m]=_daily(rows,tq,lf,m)
  base=_path_metrics(series["baseline"]);modes={}
  for m in MODES:
   x=_path_metrics(series[m]);modes[m]={"end_equity":x["end_equity"],"max_drawdown":x["max_drawdown"],"wealth_ratio_vs_baseline":x["end_equity"]/base["end_equity"],"maxdd_improvement_vs_baseline":x["max_drawdown"]-base["max_drawdown"],"intervention_sessions":hits[m]}
  eps={}
  for name,s,e in EPISODES:
   b=episode(rows,series["baseline"],s,e)
   if b is None:continue
   eps[name]={"start":s,"end":e,"baseline":b}
   for m in MODES[1:]:
    x=episode(rows,series[m],s,e);eps[name][m]={"end_equity":x["end_equity"],"max_drawdown":x["max_drawdown"],"wealth_ratio_vs_baseline":x["end_equity"]/b["end_equity"],"maxdd_improvement_vs_baseline":x["max_drawdown"]-b["max_drawdown"]}
  allres[str(lag)]={"modes":modes,"episodes":eps}
 r={"schema_version":1,"kind":"PULSE_VOL_LAG_COMPONENT_FORENSICS_RESEARCH_ONLY","frozen_model_mutated":False,"promotion_allowed":False,"lags_sessions":list(LAGS),"modes":list(MODES),"episodes":[{"name":n,"start":s,"end":e} for n,s,e in EPISODES],"results":allres,"anti_overfit_contract":["Existing pulse-only, vol-only and combined mechanisms only","Lag grid predeclared at 0/1/2/5 sessions","No threshold changes","Episode windows predeclared from existing major-drawdown diagnostics","Prior completed-session features only","No promotion"],"claim_boundary":"Historical component/episode falsification. Episode labels and lag outcomes are descriptive, not forecasts or promotion evidence."}
 Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

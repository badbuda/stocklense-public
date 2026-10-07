from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics
OUT=Path("research/accel_mechanism_broad_megabatch.json")
MODES=("baseline","accel_fixed","accel_10","accel_20","accel_25","accel_ratio110","accel_ratio120","downside_semivol","neg_cluster","vol_of_vol","crash_gap")
def build(out=OUT):
 rows,tq,_,_=_aligned(); d=pd.to_datetime([r["date"] for r in rows]); q=pd.Series([float(r["close"]) for r in rows],index=d); qr=q.pct_change(fill_method=None)
 rv10=qr.rolling(10,10).std()*(252**.5); rv20=qr.rolling(20,20).std()*(252**.5); rv25=qr.rolling(25,25).std()*(252**.5); rv60=qr.rolling(60,40).std()*(252**.5)
 cap=(.60/rv20.replace(0,float("nan"))).clip(1,3); downside=qr.where(qr<0,0).rolling(20,20).std()*(252**.5)
 neg5=(qr<0).rolling(5,5).sum(); vov=rv20.pct_change(5); gap=qr.rolling(5,5).min()
 flags={"accel_fixed":rv20>1.15*rv60,"accel_10":rv10>1.15*rv60,"accel_20":rv20>1.15*rv60,"accel_25":rv25>1.15*rv60,
 "accel_ratio110":rv20>1.10*rv60,"accel_ratio120":rv20>1.20*rv60,"downside_semivol":downside>.18,"neg_cluster":neg5>=4,"vol_of_vol":vov>.25,"crash_gap":gap<-.04}
 def run(mode):
  ret=[];ex=[];hits=0
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]); dt=d[i-1]; c=3.
   if mode!="baseline" and bool(flags[mode].get(dt,False)) and pd.notna(cap.get(dt)): c=float(cap[dt])
   e=min(frozen,c);ex.append(e);hits+=int(e<frozen-1e-12);q0,t0=weights_for_leverage(e) if e>0 else (0.,0.)
   rq=float(rows[i]["close"])/float(rows[i-1]["close"])-1; rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
   ret.append(TARGET_INVESTED_FRACTION*(q0*rq+t0*rt))
  return ret,ex,hits
 hist={}; series={}
 for m in MODES:
  r,e,h=run(m);series[m]=r;hist[m]={**_path_metrics(r),"mean_leverage":sum(e)/len(e),"interventions":h}
 b=hist["baseline"]; comp={}
 for m in MODES[1:]:
  x=hist[m]; comp[m]={"wealth_ratio":x["end_equity"]/b["end_equity"],"dd_improvement":x["max_drawdown"]-b["max_drawdown"],
  "continue":x["end_equity"]/b["end_equity"]>=.85 and x["max_drawdown"]-b["max_drawdown"]>=.03}
 result={"kind":"ACCEL_MECHANISM_BROAD_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,
 "primary_predeclared":"accel_fixed = RV20 > 1.15*RV60 with unchanged 60% cap",
 "sensitivity_not_selection":["accel_10","accel_25","accel_ratio110","accel_ratio120"],
 "orthogonal_families":["downside_semivol","neg_cluster","vol_of_vol","crash_gap"],
 "threshold_contract":"Coarse mechanism probes only; do not select a winner from neighboring thresholds. Any orthogonal survivor requires a fresh red-team.",
 "historical":hist,"comparisons":comp,"claim_boundary":"Research-only mechanism map; no promotion."}
 Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

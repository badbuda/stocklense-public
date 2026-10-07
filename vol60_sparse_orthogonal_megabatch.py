from __future__ import annotations
import json
from pathlib import Path
import pandas as pd
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from orthogonal_tail_validation import _path_metrics

OUT=Path("research/vol60_sparse_orthogonal_megabatch.json")
MODES=("baseline","vol60","accel_only","trend_confirm","dd_confirm","accel_trend","accel_dd")
def build(out=OUT):
 rows,tq,_,_=_aligned(); d=pd.to_datetime([r["date"] for r in rows]); q=pd.Series([float(r["close"]) for r in rows],index=d)
 qr=q.pct_change(fill_method=None); rv20=qr.rolling(20,min_periods=20).std()*(252**.5); rv60=qr.rolling(60,min_periods=40).std()*(252**.5)
 sma50=q.rolling(50,min_periods=50).mean(); sma200=q.rolling(200,min_periods=200).mean()
 dd=q/q.cummax()-1; cap=(.60/rv20.replace(0,float("nan"))).clip(1,3)
 feat=pd.DataFrame({"cap":cap,"accel":rv20>rv60*1.15,"trend":sma50<sma200,"dd":dd<-.10},index=d)
 def run(mode):
  ret=[];ex=[];hits=0
  for i in range(1,len(rows)):
   frozen=float(rows[i-1]["leverage"]); dt=d[i-1]; c=3.
   if mode!="baseline" and pd.notna(feat.at[dt,"cap"]):
    active={"vol60":True,"accel_only":bool(feat.at[dt,"accel"]),"trend_confirm":bool(feat.at[dt,"trend"]),
     "dd_confirm":bool(feat.at[dt,"dd"]),"accel_trend":bool(feat.at[dt,"accel"] and feat.at[dt,"trend"]),
     "accel_dd":bool(feat.at[dt,"accel"] and feat.at[dt,"dd"])}[mode]
    if active:c=float(feat.at[dt,"cap"])
   e=min(frozen,c);ex.append(e);hits+=int(e<frozen-1e-12)
   q0,t0=weights_for_leverage(e) if e>0 else (0.,0.); rqq=float(rows[i]["close"])/float(rows[i-1]["close"])-1; rt=float(tq[rows[i]["date"]])/float(tq[rows[i-1]["date"]])-1
   ret.append(TARGET_INVESTED_FRACTION*(q0*rqq+t0*rt))
  return ret,ex,hits
 series={}; hist={}
 for m in MODES:
  r,e,h=run(m);series[m]=r;hist[m]={**_path_metrics(r),"mean_leverage":sum(e)/len(e),"interventions":h}
 b=hist["baseline"]; gates={}
 for m in MODES[1:]:
  x=hist[m]; gates[m]={"wealth_ratio":x["end_equity"]/b["end_equity"],"dd_improvement":x["max_drawdown"]-b["max_drawdown"],
   "continue":x["end_equity"]/b["end_equity"]>=.85 and x["max_drawdown"]-b["max_drawdown"]>=.03}
 result={"kind":"VOL60_SPARSE_ORTHOGONAL_MEGABATCH_RESEARCH_ONLY","frozen_model_mutated":False,
  "contract":["60% target unchanged","confirmation thresholds declared before this batch","prior completed-session features only","no optimizer","no promotion"],
  "definitions":{"accel":"RV20 > 1.15*RV60","trend":"SMA50 < SMA200","dd":"QQQ drawdown < -10%"},
  "historical":hist,"gates":gates,"claim_boundary":"Exploratory orthogonal sparsification; requires independent red-team before any use."}
 Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

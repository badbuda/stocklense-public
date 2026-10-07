from __future__ import annotations
import json,math
from datetime import date
from pathlib import Path
from stocklens.data import load_qqq_history,load_tqqq_history
from stocklens.core import compute_features,defense_active,LEVEL_LEVERAGE,TRADING_START
from tqqq_reality_check import _hybrid_actual_l3

OUT=Path("research/frozen8_parameter_start_sensitivity.json")
BASE={"retain":0.99,"reentry":1.01,"up3":0.28,"drop3":0.32,"up2":0.38,"drop2":0.42}
# Predeclared symmetric local perturbations. Diagnostic only; no selection/ranking.
PERTURB=[
 ("BASE",{}),
 ("TREND_TIGHT",{"retain":0.995,"reentry":1.015}),
 ("TREND_LOOSE",{"retain":0.985,"reentry":1.005}),
 ("VOL_LOW",{"up3":0.26,"drop3":0.30,"up2":0.36,"drop2":0.40}),
 ("VOL_HIGH",{"up3":0.30,"drop3":0.34,"up2":0.40,"drop2":0.44}),
]
STARTS=("2011-01-03","2012-01-03","2014-01-02","2016-01-04","2018-01-02","2020-01-02")

def _next(f,prev,p):
    prev=prev if prev is not None else 1
    risk_on=prev>1
    trend=f.close>=f.sma200*p["retain"] if risk_on else f.close>f.sma200*p["reentry"]
    if not trend:return 1
    if prev==3:return 2 if f.vol20>=p["drop3"] else 3
    if prev==2:
        if f.vol20<p["up3"]:return 3
        if f.vol20>=p["drop2"]:return 1
        return 2
    if f.vol20<p["up3"]:return 3
    if f.vol20<p["up2"]:return 2
    return 1

def _rows(df,p):
    dates=df["Date"].dt.date.astype(str).tolist();closes=df["Close"].astype(float).tolist()
    level=None;out=[];prev=None
    for i,d in enumerate(dates):
        if date.fromisoformat(d)<TRADING_START or i<252:continue
        f=compute_features(closes[:i+1]);level=_next(f,level,p);lev=0.0 if defense_active(f) else float(LEVEL_LEVERAGE[level])
        out.append({"date":d,"close":closes[i],"leverage":lev,"level":level,"event":prev is not None and lev!=prev})
        prev=lev
    return out

def build(out=OUT):
    q,qa=load_qqq_history();t,ta=load_tqqq_history();tmap={d.date().isoformat():float(c) for d,c in zip(t["Date"],t["Close"])}
    variants=[]
    for name,delta in PERTURB:
        p={**BASE,**delta}; rows=[r for r in _rows(q,p) if r["date"] in tmap and r["date"]>="2010-02-09"]
        m=_hybrid_actual_l3(rows,tmap,5,0)
        variants.append({"variant":name,"parameters":p,"sessions":len(rows),"transition_count":sum(bool(r["event"]) for r in rows),**m})
    base_rows=[r for r in _rows(q,BASE) if r["date"] in tmap and r["date"]>="2010-02-09"]
    starts=[]
    for st in STARTS:
        rr=[r for r in base_rows if r["date"]>=st]
        if len(rr)>=252: starts.append({"requested_start":st,"actual_start":rr[0]["date"],"sessions":len(rr),**_hybrid_actual_l3(rr,tmap,5,0)})
    cagrs=[x["cagr"] for x in variants]
    result={"schema_version":1,"status":"PASS","kind":"FROZEN8_LOCAL_PARAMETER_AND_START_DATE_SENSITIVITY",
      "promotion_allowed":False,"retuning_authorized":False,"frozen_model_mutated":False,
      "selection_policy":"NO_WINNER_SELECTION_NO_PARAMETER_PROMOTION_PREDECLARED_LOCAL_PERTURBATIONS_ONLY",
      "execution_semantics":"Observed adjusted TQQQ returns only at 3x exposure; other exposures remain QQQ-times-target synthetic; 5 bps turnover cost.",
      "baseline_parameters":BASE,"parameter_variants":variants,"start_date_sensitivity":starts,
      "parameter_distribution":{"variants":len(variants),"min_cagr":min(cagrs),"max_cagr":max(cagrs),"spread":max(cagrs)-min(cagrs),
        "all_finite":all(math.isfinite(x) for x in cagrs)},
      "claim_boundary":"Sensitivity diagnostic around frozen rules. Variants are deliberately not ranked or selected and cannot modify StockLens 8.0."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

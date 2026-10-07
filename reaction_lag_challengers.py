from __future__ import annotations
import json, math
from pathlib import Path
from datetime import date
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
OUT=Path("research/reaction_lag_challengers.json")

# Predeclared before this module observes outcome metrics.
RULES=(
 ("baseline",None,None),
 ("peak_dd_08_cap2",0.08,2.0),
 ("peak_dd_10_cap2",0.10,2.0),
 ("peak_dd_12_cap2",0.12,2.0),
)

def _run(rows,tq,trigger,cap,cost_bps=5):
    nav=peak_nav=100000.; peak_close=float(rows[0]["close"]); dd=0.;prev=(0.,0.);costs=0.;hits=0
    for i in range(1,len(rows)):
        src=rows[i-1]; peak_close=max(peak_close,float(src["close"]))
        market_dd=float(src["close"])/peak_close-1
        exp=float(src["leverage"])
        if trigger is not None and market_dd<=-trigger and exp>cap: exp=cap;hits+=1
        q0,t0=weights_for_leverage(exp) if exp>0 else (0.,0.);q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
        qr=float(rows[i]["close"])/float(rows[i-1]["close"])-1;tr=tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1
        nav*=1+q*qr+t*tr;turn=abs(q-prev[0])+abs(t-prev[1]);fee=nav*turn*cost_bps/10000;nav-=fee;costs+=fee
        peak_nav=max(peak_nav,nav);dd=min(dd,nav/peak_nav-1);prev=(q,t)
    years=(date.fromisoformat(rows[-1]["date"])-date.fromisoformat(rows[0]["date"])).days/365.2425
    return {"end_equity":nav,"cagr":(nav/100000.)**(1/years)-1,"max_drawdown":dd,"estimated_turnover_cost":costs,"sessions_actually_capped":hits}

def build(out=OUT):
    rows,tq,_,_=_aligned()
    results=[]
    for name,trig,cap in RULES:
        results.append({"name":name,"qqq_drawdown_trigger":trig,"cap":cap,**_run(rows,tq,trig,cap)})
    base=results[0]
    for item in results:
        item["cagr_delta_vs_baseline"]=item["cagr"]-base["cagr"]
        item["maxdd_delta_vs_baseline"]=item["max_drawdown"]-base["max_drawdown"]
    splits={"development":{"start":"2010-02-11","end":"2017-12-31"},"validation":{"start":"2018-01-01","end":"2026-09-30"}}
    split_results={}
    for label,sp in splits.items():
        subset=[r for r in rows if sp["start"]<=r["date"]<=sp["end"]]
        split_results[label]=[{"name":name,**_run(subset,tq,trig,cap)} for name,trig,cap in RULES]
    result={"schema_version":1,"kind":"REACTION_LAG_CHALLENGERS_RESEARCH_ONLY","promotion_allowed":False,"frozen_model_mutated":False,
      "predeclared_rules":[{"name":name,"qqq_drawdown_trigger":trig,"cap":cap} for name,trig,cap in RULES],
      "results":results,"time_splits":splits,"split_results":split_results,
      "claim_boundary":"Exploratory execution-layer challengers only. Frozen StockLens signals are unchanged. The rule family was motivated by full-history diagnostics, so validation is robustness evidence, not a pristine untouched holdout; no automatic promotion."}
    Path(out).write_text(json.dumps(result,indent=2)+"\\n")
    return result

if __name__=="__main__":print(json.dumps(build(),indent=2))

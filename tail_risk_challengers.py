from __future__ import annotations
import json, math
from pathlib import Path
from datetime import date
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned

OUT=Path("research/tail_risk_challengers.json")
# Predeclared, simple execution overlays. Frozen StockLens decisions are never changed.
CAPS=(("baseline",3.0,None),("vol_cap_032",2.0,0.32),("vol_cap_028",2.0,0.28))

def _run(rows,tq,cap,threshold,cost_bps=5):
    nav=peak=100000.0; dd=0.0; prev_q=prev_t=0.0; total_cost=0.0
    for i in range(1,len(rows)):
        src=rows[i-1]; exp=float(src["leverage"])
        if "vol20" not in src: raise RuntimeError("MISSING_FROZEN_VOL20")
        vol=float(src["vol20"])
        if threshold is not None and vol>=threshold: exp=min(exp,cap)
        qret=float(rows[i]["close"])/float(rows[i-1]["close"])-1
        tret=tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1
        if exp<=0:q=t=0.0
        else:
            q0,t0=weights_for_leverage(exp);q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
        nav*=1+q*qret+t*tret
        turnover=abs(q-prev_q)+abs(t-prev_t); cost=nav*turnover*cost_bps/10000
        nav-=cost;total_cost+=cost;peak=max(peak,nav);dd=min(dd,nav/peak-1);prev_q,prev_t=q,t
        if nav<=0 or not math.isfinite(nav):raise RuntimeError("CAPITAL_DEPLETED")
    years=(date.fromisoformat(rows[-1]["date"])-date.fromisoformat(rows[0]["date"])).days/365.2425
    return {"end_equity":nav,"cagr":(nav/100000)**(1/years)-1,"max_drawdown":dd,"estimated_turnover_cost":total_cost}

def _activation_diagnostics(rows,threshold):
    hits=[]
    for r in rows[:-1]:
        if threshold is not None and float(r["vol20"])>=threshold:
            hits.append(float(r["leverage"]))
    return {"sessions":len(hits),"leverage_counts":{str(x):sum(v==x for v in hits) for x in (0.0,1.25,2.0,3.0)},
      "sessions_actually_capped":sum(v>2.0 for v in hits)}

def build(out=OUT):
    rows,tq,qa,ta=_aligned()
    results=[{"name":name,"cap":cap,"vol20_threshold":thr,**_run(rows,tq,cap,thr)} for name,cap,thr in CAPS]
    base=results[0]
    for x in results:
        x["cagr_delta_vs_baseline"]=x["cagr"]-base["cagr"];x["maxdd_delta_vs_baseline"]=x["max_drawdown"]-base["max_drawdown"]
    result={"schema_version":1,"status":"PASS","kind":"TAIL_RISK_CHALLENGERS_RESEARCH_ONLY",
      "promotion_allowed":False,"frozen_model_mutated":False,
      "predeclared_candidates":[{"name":n,"cap":c,"vol20_threshold":t} for n,c,t in CAPS],
      "results":results,
      "activation_counts":{name:sum(1 for r in rows[:-1] if thr is not None and float(r["vol20"])>=thr) for name,cap,thr in CAPS},
      "activation_diagnostics":{name:_activation_diagnostics(rows,thr) for name,cap,thr in CAPS if thr is not None},
      "claim_boundary":"Exploratory parallel challengers only. Thresholds are predeclared before observing this run's challenger results; no automatic promotion and no StockLens 8.0 signal mutation."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

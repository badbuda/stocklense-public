from __future__ import annotations
import json, math
from pathlib import Path
from datetime import date
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned

OUT=Path("research/tradable_blend_challenger.json")

def _run(rows,tq,cost_bps=5):
    nav=peak=100000.0; dd=0.0; total_cost=0.0
    prev_q=prev_t=0.0
    for i in range(1,len(rows)):
        exp=float(rows[i-1]["leverage"])
        qret=float(rows[i]["close"])/float(rows[i-1]["close"])-1.0
        tret=tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1.0
        if exp<=0: q=t=0.0
        else:
            q0,t0=weights_for_leverage(exp)
            q=q0*TARGET_INVESTED_FRACTION; t=t0*TARGET_INVESTED_FRACTION
        market=q*qret+t*tret
        nav*=1.0+market
        turnover=abs(q-prev_q)+abs(t-prev_t)
        cost=nav*turnover*cost_bps/10000.0
        nav-=cost; total_cost+=cost
        peak=max(peak,nav); dd=min(dd,nav/peak-1.0)
        prev_q,prev_t=q,t
        if nav<=0 or not math.isfinite(nav): raise RuntimeError("CAPITAL_DEPLETED")
    years=(date.fromisoformat(rows[-1]["date"])-date.fromisoformat(rows[0]["date"])).days/365.2425
    return {"end_equity":nav,"cagr":(nav/100000.0)**(1/years)-1.0,"max_drawdown":dd,
      "estimated_turnover_cost":total_cost}

def build(out=OUT):
    rows,tq,qa,ta=_aligned()
    ladder=[{"cost_bps":b,**_run(rows,tq,b)} for b in (5,10,25,50,100)]
    result={"schema_version":1,"status":"PASS","kind":"TRADABLE_BLEND_CHALLENGER_RESEARCH_ONLY",
      "promotion_allowed":False,"frozen_model_mutated":False,
      "semantics":"Frozen StockLens 8.0 signals; prior-session target mapped to QQQ/TQQQ weights via existing weights_for_leverage, with 1.5% buffer. Adjusted-close daily returns; no broker execution claim.",
      "period":{"start":rows[0]["date"],"end":rows[-1]["date"],"sessions":len(rows)},
      "cost_ladder":ladder,
      "claim_boundary":"Research execution approximation only. Same frozen signal path; this changes execution representation, not StockLens 8.0 decisions."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n"); return result

if __name__=="__main__": print(json.dumps(build(),indent=2))

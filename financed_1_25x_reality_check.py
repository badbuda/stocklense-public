from __future__ import annotations
import json
from pathlib import Path
from leveraged_instrument_reality_check import _load,_run
from tqqq_reality_check import _aligned

OUT=Path("research/financed_1_25x_reality_check.json")
ANNUAL_RATES=(0.0,0.02,0.04,0.06,0.08,0.10)
BORROWED_FRACTION=0.25

def _financed(rows,tqqq,qld,annual_rate,cost_bps=5):
    x=_run(rows,tqqq,qld,cost_bps,0)
    # Recompute path with explicit daily financing drag only while target exposure is 1.25x.
    nav=peak=100000.0;dd=0.0;prev=0.0;finance=0.0;n125=0
    for i in range(1,len(rows)):
        exp=float(rows[i-1]["leverage"]);d0=rows[i-1]["date"];d1=rows[i]["date"]
        q=float(rows[i]["close"])/float(rows[i-1]["close"])-1.0
        if exp==3.0 and d0 in tqqq and d1 in tqqq:r=tqqq[d1]/tqqq[d0]-1.0
        elif exp==2.0 and d0 in qld and d1 in qld:r=qld[d1]/qld[d0]-1.0
        else:r=q*exp
        nav*=1+r
        if exp==1.25:
            charge=nav*BORROWED_FRACTION*annual_rate/252.0;nav-=charge;finance+=charge;n125+=1
        turnover=abs(exp-prev);nav-=nav*turnover*cost_bps/10000
        peak=max(peak,nav);dd=min(dd,nav/peak-1);prev=exp
    from datetime import date
    years=(date.fromisoformat(rows[-1]["date"])-date.fromisoformat(rows[0]["date"])).days/365.2425
    return {"annual_financing_rate":annual_rate,"borrowed_fraction_at_1_25x":BORROWED_FRACTION,
      "end_equity":nav,"cagr":(nav/100000)**(1/years)-1,"max_drawdown":dd,
      "estimated_financing_cost":finance,"financed_1_25x_intervals":n125,
      "unfinanced_reference_end_equity":x["end_equity"]}

def build(out=OUT):
    rows,tqqq,_,_=_aligned();qld=_load("QLD","2006-06-21")
    scenarios=[_financed(rows,tqqq,qld,r) for r in ANNUAL_RATES]
    x={"schema_version":1,"status":"PASS","kind":"FINANCED_1_25X_EXECUTION_REALITY_CHECK",
      "promotion_allowed":False,"retuning_authorized":False,"frozen_model_mutated":False,
      "selection":"NONE_FIXED_FINANCING_STRESS_GRID","scenarios":scenarios,
      "claim_boundary":"Financing sensitivity only, not a forecast or broker quote. Applies a fixed annualized financing charge to the 25% borrowed sleeve only when frozen exposure is 1.25x; TQQQ/QLD adjusted prices already embed fund-level expenses. Taxes, borrow availability, spread and intraday fills remain outside this model."}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

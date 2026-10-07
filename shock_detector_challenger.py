from __future__ import annotations
import json
from pathlib import Path
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from research_metrics import evaluate_daily_returns
OUT=Path("research/shock_detector_challenger.json")
RULES=(("baseline",0,None),("shock_1d_04",1,-.04),("shock_3d_07",3,-.07),("shock_5d_10",5,-.10))

def _run(rows,tq,window,threshold,cost_bps=5):
    nav=100000.;prev_q=prev_t=0.;rets=[];costs=0.;hits=0
    for i in range(1,len(rows)):
        src=rows[i-1];exp=float(src["leverage"])
        hit=False
        if window and i-1>=window:
            shock=float(src["close"])/float(rows[i-1-window]["close"])-1
            hit=shock<=threshold and exp>2
        exec_exp=2.0 if hit else exp;hits+=int(hit)
        q0,t0=weights_for_leverage(exec_exp) if exec_exp>0 else (0.,0.)
        q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
        qr=float(rows[i]["close"])/float(rows[i-1]["close"])-1
        tr=tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1
        before=nav;nav*=1+q*qr+t*tr
        cost=nav*(abs(q-prev_q)+abs(t-prev_t))*cost_bps/10000.;nav-=cost;costs+=cost
        rets.append(nav/before-1);prev_q,prev_t=q,t
    return {"end_equity":nav,"intervention_sessions":hits,"estimated_turnover_cost":costs,**evaluate_daily_returns(rets)}

def build(out=OUT):
    rows,tq,_,_=_aligned();splits={"development":("2010-02-11","2017-12-31"),"validation":("2018-01-01","2026-09-30")}
    full=[{"name":n,"window":w,"threshold":th,**_run(rows,tq,w,th)} for n,w,th in RULES]
    split={}
    for label,(a,b) in splits.items():
        rr=[r for r in rows if a<=r["date"]<=b]
        split[label]=[{"name":n,**_run(rr,tq,w,th)} for n,w,th in RULES]
    result={"schema_version":1,"kind":"TR_SHOCK_001_RESEARCH_ONLY","frozen_model_mutated":False,"promotion_allowed":False,
      "rules":[{"name":n,"window_sessions":w,"qqq_return_threshold":th} for n,w,th in RULES],
      "results":full,"time_splits":splits,"split_results":split,
      "semantics":"Prior-session QQQ shock only; if triggered while frozen leverage >2x, execution exposure is capped at 2x for the next session. Frozen signal is unchanged.",
      "claim_boundary":"Historically motivated exploratory overlay; not pristine holdout evidence, forecast, or production rule."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

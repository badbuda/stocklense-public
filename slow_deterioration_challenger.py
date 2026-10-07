from __future__ import annotations
import json
from pathlib import Path
from stocklens.core import weights_for_leverage,TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned
from research_metrics import evaluate_daily_returns
OUT=Path("research/slow_deterioration_challenger.json")
RULES=(
 ("baseline",None),
 ("slow_21d_08",{"ret21":-.08,"sma_drop":-.04,"mom_drop":-.08}),
 ("slow_21d_10",{"ret21":-.10,"sma_drop":-.05,"mom_drop":-.10}),
)

def _run(rows,tq,rule,cost_bps=5):
    nav=100000.;prev_q=prev_t=0.;rets=[];costs=0.;hits=0
    for i in range(1,len(rows)):
        src=rows[i-1];exp=float(src["leverage"]);hit=False
        if rule and i-1>=21 and exp>2:
            old=rows[i-1-21]
            ret21=float(src["close"])/float(old["close"])-1
            sma_now=float(src["close"])/float(src["sma200"])-1
            sma_old=float(old["close"])/float(old["sma200"])-1
            mom_drop=float(src["mom12"])-float(old["mom12"])
            # Persistent deterioration requires market loss plus deterioration in either trend distance or momentum.
            hit=ret21<=rule["ret21"] and ((sma_now-sma_old)<=rule["sma_drop"] or mom_drop<=rule["mom_drop"])
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
    full=[{"name":n,**_run(rows,tq,r)} for n,r in RULES];split={}
    for label,(a,b) in splits.items():
        rr=[x for x in rows if a<=x["date"]<=b]
        split[label]=[{"name":n,**_run(rr,tq,r)} for n,r in RULES]
    result={"schema_version":1,"kind":"TR_SLOW_001_RESEARCH_ONLY","frozen_model_mutated":False,"promotion_allowed":False,
      "rules":[{"name":n,"criteria":r} for n,r in RULES],"results":full,"time_splits":splits,"split_results":split,
      "semantics":"Prior-session 21-session QQQ loss plus deterioration in SMA200 distance or MOM12; cap next-session execution at 2x only while frozen leverage remains >2x. Frozen signal unchanged.",
      "claim_boundary":"Historically motivated exploratory overlay; not pristine holdout evidence, forecast, or production rule."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

from __future__ import annotations
import json, math
from pathlib import Path
from stocklens.data import load_qqq_history, load_tqqq_history
from yahoo_long_history import _rows
from backtest_engine import run_backtest
from backtest_contract import FrozenExposureReplayAdapter, stocklens_8_request

OUT=Path("research/tqqq_reality_check.json")

def _aligned():
    qdf,qa=load_qqq_history(); tdf,ta=load_tqqq_history()
    rows,_=_rows(qdf,qa)
    t={d.date().isoformat():float(c) for d,c in zip(tdf["Date"],tdf["Close"])}
    rows=[r for r in rows if r["date"] in t and r["date"]>="2010-02-09"]
    if len(rows)<3000: raise RuntimeError("INSUFFICIENT_TQQQ_OVERLAP")
    return rows,t,qa,ta

def _three_x_tracking(rows,tqqq):
    samples=[]; synth=actual=1.0
    for i in range(1,len(rows)):
        if float(rows[i-1]["leverage"])!=3.0: continue
        q=float(rows[i]["close"])/float(rows[i-1]["close"])-1
        a=tqqq[rows[i]["date"]]/tqqq[rows[i-1]["date"]]-1
        s=3.0*q
        samples.append(a-s); synth*=1+s; actual*=1+a
    mean=sum(samples)/len(samples)
    rmse=math.sqrt(sum(x*x for x in samples)/len(samples))
    return {"sessions":len(samples),"mean_daily_actual_minus_synthetic":mean,"rmse_daily":rmse,
      "compounded_actual_tqqq_on_l3_sessions":actual-1,"compounded_synthetic_3x_qqq_on_l3_sessions":synth-1,
      "actual_to_synthetic_growth_ratio":actual/synth if synth else None}

def _delay_rows(rows,days):
    out=[]
    for i,r in enumerate(rows):
        j=max(0,i-days)
        out.append(dict(r,leverage=float(rows[j]["leverage"]),event=(i>0 and float(rows[j]["leverage"])!=float(out[-1]["leverage"]))))
    return out


def _hybrid_actual_l3(rows,tqqq,cost_bps=5,delay=0):
    execution_rows=_delay_rows(rows,delay)
    nav=peak=100000.0; maxdd=0.0; total_cost=0.0; prev_exp=0.0
    for i in range(1,len(rows)):
        exp=float(execution_rows[i-1]["leverage"])
        qret=float(rows[i]["close"])/float(rows[i-1]["close"])-1.0
        if exp==3.0:
            market_ret=tqqq[rows[i]["date"]]/tqqq[rows[i-1]["date"]]-1.0
        else:
            market_ret=qret*exp
        nav*=1.0+market_ret
        turnover=abs(exp-prev_exp)
        cost=nav*turnover*float(cost_bps)/10000.0
        nav-=cost; total_cost+=cost; peak=max(peak,nav); maxdd=min(maxdd,nav/peak-1.0); prev_exp=exp
        if not math.isfinite(nav) or nav<=0: raise RuntimeError("HYBRID_CAPITAL_DEPLETED")
    years=(__import__("datetime").date.fromisoformat(rows[-1]["date"])-__import__("datetime").date.fromisoformat(rows[0]["date"])).days/365.2425
    return {"end_equity":nav,"cagr":(nav/100000.0)**(1/years)-1.0,"max_drawdown":maxdd,"estimated_turnover_cost":total_cost}

def build(out=OUT):
    rows,tqqq,qa,ta=_aligned(); adapter=FrozenExposureReplayAdapter()
    cost=[]; delay=[]
    for bps in (5,10,25,50,100):
        r=run_backtest(rows,stocklens_8_request(initial=100000,monthly=0,cost_bps=bps),adapter)
        cost.append({"cost_bps":bps,"cagr":r["analytics"]["cagr_without_contribution_distortion"],"max_drawdown":r["max_drawdown"],"end_equity":r["end_equity"]})
    for d in (0,1,2,5):
        rr=_delay_rows(rows,d)
        r=run_backtest(rr,stocklens_8_request(initial=100000,monthly=0,cost_bps=5),adapter)
        delay.append({"decision_delay_sessions":d,"cagr":r["analytics"]["cagr_without_contribution_distortion"],"max_drawdown":r["max_drawdown"],"end_equity":r["end_equity"]})
    hybrid_cost=[{"cost_bps":b,**_hybrid_actual_l3(rows,tqqq,b,0)} for b in (5,10,25,50,100)]
    hybrid_delay=[{"decision_delay_sessions":d,**_hybrid_actual_l3(rows,tqqq,5,d)} for d in (0,1,2,5)]
    result={"schema_version":1,"status":"PASS","kind":"TQQQ_REALITY_CHECK_RESEARCH_ONLY",
      "promotion_allowed":False,"frozen_model_mutated":False,
      "period":{"start":rows[0]["date"],"end":rows[-1]["date"],"sessions":len(rows)},
      "observed_tqqq":{"source_audit":ta,"usage":"TRACKING_DIAGNOSTIC_ON_LEVEL_3_SESSIONS_ONLY"},
      "qqq_source_audit":qa,"three_x_tracking":_three_x_tracking(rows,tqqq),
      "synthetic_execution_stress":{"cost_ladder":cost,"decision_delay":delay},"hybrid_actual_l3_stress":{"semantics":"Uses the same delayed frozen exposure stream as synthetic stress. Actual TQQQ adjusted-close returns are used only when execution exposure equals 3.0; other exposures remain QQQ-return-times-target synthetic.","cost_ladder":hybrid_cost,"decision_delay":hybrid_delay},
      "claim_boundary":"Observed TQQQ is used only to measure 3x tracking on sessions where frozen StockLens targets level 3. Mixed 0/1.25/2/3x portfolio execution remains synthetic and is not claimed as actual TQQQ execution."}
    Path(out).write_text(json.dumps(result,indent=2)+chr(10));return result

if __name__=="__main__": print(json.dumps(build(),indent=2))

from __future__ import annotations
import json,math
from pathlib import Path
import pandas as pd
import yfinance as yf
from tqqq_reality_check import _aligned,_delay_rows

OUT=Path("research/leveraged_instrument_reality_check.json")

def _load(symbol,start):
    df=yf.download(symbol,start=start,interval="1d",auto_adjust=True,progress=False,actions=False,threads=False)
    if df is None or df.empty: raise RuntimeError("NO_"+symbol+"_DATA")
    c=df["Close"][symbol] if isinstance(df.columns,pd.MultiIndex) else df["Close"]
    return {pd.Timestamp(d).date().isoformat():float(v) for d,v in zip(c.index,c.values) if math.isfinite(float(v)) and float(v)>0}

def _run(rows,tqqq,qld,cost_bps=5,delay=0):
    ex=_delay_rows(rows,delay); nav=peak=100000.0;dd=0.0;costs=0.0;prev=0.0;actual3=actual2=synthetic125=0
    for i in range(1,len(rows)):
        exp=float(ex[i-1]["leverage"]); d0=rows[i-1]["date"];d1=rows[i]["date"]
        q=float(rows[i]["close"])/float(rows[i-1]["close"])-1.0
        if exp==3.0 and d0 in tqqq and d1 in tqqq:
            r=tqqq[d1]/tqqq[d0]-1.0;actual3+=1
        elif exp==2.0 and d0 in qld and d1 in qld:
            r=qld[d1]/qld[d0]-1.0;actual2+=1
        else:
            r=q*exp
            if exp==1.25: synthetic125+=1
        nav*=1+r
        turnover=abs(exp-prev);c=nav*turnover*cost_bps/10000;nav-=c;costs+=c
        peak=max(peak,nav);dd=min(dd,nav/peak-1);prev=exp
    years=(__import__("datetime").date.fromisoformat(rows[-1]["date"])-__import__("datetime").date.fromisoformat(rows[0]["date"])).days/365.2425
    return {"end_equity":nav,"cagr":(nav/100000)**(1/years)-1,"max_drawdown":dd,"estimated_turnover_cost":costs,
      "observed_tqqq_3x_intervals":actual3,"observed_qld_2x_intervals":actual2,"synthetic_1_25x_intervals":synthetic125}

def build(out=OUT):
    rows,tqqq,_,_=_aligned();qld=_load("QLD","2006-06-21")
    cost=[{"cost_bps":b,**_run(rows,tqqq,qld,b,0)} for b in (5,10,25,50,100)]
    delay=[{"decision_delay_sessions":d,**_run(rows,tqqq,qld,5,d)} for d in (0,1,2,5)]
    x={"schema_version":1,"status":"PASS","kind":"OBSERVED_LEVERAGED_INSTRUMENT_REALITY_CHECK","promotion_allowed":False,
      "retuning_authorized":False,"frozen_model_mutated":False,
      "instrument_semantics":{"3x":"observed TQQQ adjusted close","2x":"observed QLD adjusted close","1.25x":"QQQ return times 1.25; still synthetic","0x":"cash"},
      "cost_ladder":cost,"decision_delay":delay,
      "claim_boundary":"Execution-realism falsification only. Adjusted ETF prices include fund-level drag for TQQQ/QLD. The 1.25x sleeve remains synthetic and does not yet model explicit financing; taxes, spread and intraday fills are not represented."}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

from __future__ import annotations
import json
from pathlib import Path
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION
from tqqq_reality_check import _aligned

OUT=Path("research/drawdown_forensics.json")

def _series(rows,tq):
    nav=peak=1.0; out=[]
    for i in range(1,len(rows)):
        src=rows[i-1]; exp=float(src["leverage"])
        q0,t0=weights_for_leverage(exp) if exp>0 else (0.0,0.0)
        q=q0*TARGET_INVESTED_FRACTION;t=t0*TARGET_INVESTED_FRACTION
        qr=float(rows[i]["close"])/float(rows[i-1]["close"])-1
        tr=tq[rows[i]["date"]]/tq[rows[i-1]["date"]]-1
        nav*=1+q*qr+t*tr; peak=max(peak,nav)
        out.append({"date":rows[i]["date"],"nav":nav,"drawdown":nav/peak-1,
          "prior_leverage":exp,"vol20":float(src["vol20"]),"sma_ratio":float(src["close"])/float(src["sma200"])-1,
          "mom12":float(src["mom12"])})
    return out

def _episodes(s):
    episodes=[];start=None;peak_nav=1.0;trough=None
    for i,x in enumerate(s):
        if x["drawdown"]<0 and start is None:start=i;trough=i
        if start is not None and x["drawdown"]<s[trough]["drawdown"]:trough=i
        if start is not None and x["drawdown"]>=0:
            episodes.append((start,trough,i));start=None;trough=None
    if start is not None:episodes.append((start,trough,None))
    return episodes

def build(out=OUT):
    rows,tq,_,_=_aligned()
    s=_series(rows,tq); eps=_episodes(s)
    ranked=sorted(eps,key=lambda z:s[z[1]]["drawdown"])[:10]; details=[]
    for a,t,r in ranked:
        pre=s[a]; trough=s[t]
        delev=next((j for j in range(a,t+1) if s[j]["prior_leverage"]<3.0),None)
        details.append({"start":pre["date"],"trough":trough["date"],"recovery":s[r]["date"] if r is not None else None,
          "max_drawdown":trough["drawdown"],"start_state":{k:pre[k] for k in ("prior_leverage","vol20","sma_ratio","mom12")},
          "trough_state":{k:trough[k] for k in ("prior_leverage","vol20","sma_ratio","mom12")},
          "sessions_to_first_below_3x":None if delev is None else delev-a,
          "sessions_peak_to_trough":t-a,"sessions_to_recovery":None if r is None else r-a})
    result={"schema_version":1,"kind":"DRAWDOWN_FORENSICS_RESEARCH_ONLY","frozen_model_mutated":False,
      "execution_semantics":"Frozen prior-session signal mapped to QQQ/TQQQ adjusted-close blend; no costs, for drawdown mechanism diagnostics only.",
      "top_drawdown_episodes":details}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

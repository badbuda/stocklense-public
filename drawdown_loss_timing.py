from __future__ import annotations
import json
from pathlib import Path
from drawdown_forensics import _series,_episodes
from tqqq_reality_check import _aligned
OUT=Path("research/drawdown_loss_timing.json")
HORIZONS=(1,3,5,10,21)

def build(out=OUT):
    rows,tq,_,_=_aligned();s=_series(rows,tq);eps=_episodes(s)
    ranked=sorted(eps,key=lambda z:s[z[1]]["drawdown"])[:10];events=[]
    for a,t,r in ranked:
        start_nav=s[a]["nav"];trough_nav=s[t]["nav"];total=trough_nav/start_nav-1
        marks={}
        for h in HORIZONS:
            j=min(a+h,t);loss=s[j]["nav"]/start_nav-1
            marks[str(h)]={"portfolio_return":loss,"share_of_peak_to_trough_loss":None if total==0 else loss/total,
              "leverage":s[j]["prior_leverage"],"vol20":s[j]["vol20"],"sma200_distance":s[j]["sma_ratio"],"mom12":s[j]["mom12"]}
        events.append({"start":s[a]["date"],"trough":s[t]["date"],"peak_to_trough_return":total,
          "sessions_peak_to_trough":t-a,"early_loss_timing":marks})
    result={"schema_version":1,"kind":"DRAWDOWN_LOSS_TIMING_DIAGNOSTIC","frozen_model_mutated":False,
      "horizons_sessions":list(HORIZONS),"events":events,
      "claim_boundary":"Descriptive diagnostics on the historical tradable-blend replay only; not a trading rule, forecast, or promotion evidence."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

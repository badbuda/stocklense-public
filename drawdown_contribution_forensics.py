from __future__ import annotations
import json
from pathlib import Path
from drawdown_forensics import _series,_episodes
from tqqq_reality_check import _aligned
OUT=Path("research/drawdown_contribution_forensics.json")

def build(out=OUT):
    rows,tq,_,_=_aligned();s=_series(rows,tq);eps=_episodes(s)
    ranked=sorted(eps,key=lambda z:s[z[1]]["drawdown"])[:10];events=[]
    for a,t,r in ranked:
        daily=[]
        prev=s[a-1]["nav"] if a else 1.0
        for j in range(a,t+1):
            ret=s[j]["nav"]/prev-1;prev=s[j]["nav"]
            daily.append({"date":s[j]["date"],"return":ret,"leverage":s[j]["prior_leverage"]})
        losses=[x for x in daily if x["return"]<0]
        total_loss=sum(-x["return"] for x in losses) or 1.0
        by_lev={str(k):sum(-x["return"] for x in losses if x["leverage"]==k)/total_loss for k in (0.0,1.25,2.0,3.0)}
        worst=sorted(losses,key=lambda x:x["return"])[:10]
        events.append({"start":s[a]["date"],"trough":s[t]["date"],"max_drawdown":s[t]["drawdown"],
          "loss_share_by_prior_leverage":by_lev,"worst_loss_sessions":worst,
          "negative_sessions":len(losses),"sessions_peak_to_trough":t-a})
    result={"schema_version":1,"kind":"DRAWDOWN_CONTRIBUTION_FORENSICS","frozen_model_mutated":False,
      "top_drawdown_episodes":events,
      "claim_boundary":"Descriptive attribution of historical tradable-blend drawdowns; arithmetic loss-share diagnostic, not causal attribution, forecast, or trading rule."}
    Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

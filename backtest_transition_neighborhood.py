from __future__ import annotations
import json
from pathlib import Path
def build(workbench="docs/workbench.json",out="docs/backtest_transition_neighborhood.json"):
    w=json.loads(Path(workbench).read_text());rows=w.get("replay",{}).get("rows") or []
    if len(rows)<20:raise RuntimeError("TRANSITION_NEIGHBORHOOD_REPLAY_MISSING")
    events=[]
    for i in range(1,len(rows)):
        if float(rows[i]["leverage"])==float(rows[i-1]["leverage"]):continue
        path=[]
        for j in range(max(1,i-3),min(len(rows),i+4)):
            p,c=rows[j-1],rows[j];path.append({"offset":j-i,"date":c["date"],"qqq_return":float(c["close"])/float(p["close"])-1,"applied_exposure":float(p["leverage"])})
        events.append({"transition_date":rows[i]["date"],"from_exposure":float(rows[i-1]["leverage"]),"to_exposure":float(rows[i]["leverage"]),"window":path})
    x={"schema_version":1,"status":"PASS","transition_count":len(events),"radius_sessions":3,"events":events,"semantics":"Event-window evidence around exposure transitions, offsets -3..+3 where available. Descriptive timing diagnostic only; overlapping event windows are not independent observations.","automatic_promotion":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

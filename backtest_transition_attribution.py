from __future__ import annotations
import json
from pathlib import Path
from publication_identity import identity
def build(workbench="docs/workbench.json",out="docs/backtest_transition_attribution.json"):
    w=json.loads(Path(workbench).read_text());rows=w.get("replay",{}).get("rows") or []
    if len(rows)<20:raise RuntimeError("TRANSITION_ATTRIBUTION_REPLAY_MISSING")
    transitions=[]
    for i in range(1,len(rows)):
        p,c=rows[i-1],rows[i]
        if float(c["leverage"])==float(p["leverage"]):continue
        q=float(c["close"])/float(p["close"])-1
        nxt=None
        if i+1<len(rows):nxt=float(rows[i+1]["close"])/float(c["close"])-1
        transitions.append({"date":c["date"],"from_exposure":float(p["leverage"]),"to_exposure":float(c["leverage"]),"same_session_qqq_return":q,"next_session_qqq_return":nxt,"direction":"UP" if float(c["leverage"])>float(p["leverage"]) else "DOWN"})
    ups=[x for x in transitions if x["direction"]=="UP"];downs=[x for x in transitions if x["direction"]=="DOWN"]
    def avg(xs,k):
        v=[x[k] for x in xs if x[k] is not None];return sum(v)/len(v) if v else None
    x={"schema_version":1,"publication_identity":identity(),"status":"PASS","transition_count":len(transitions),"upshift_count":len(ups),"downshift_count":len(downs),"upshift_avg_next_session_qqq_return":avg(ups,"next_session_qqq_return"),"downshift_avg_next_session_qqq_return":avg(downs,"next_session_qqq_return"),"transitions":transitions,"semantics":"Descriptive transition timing audit only. Same/next-session averages are not causal estimates and must not be used to retune frozen 8.0.","automatic_promotion":False,"retuning_authorized":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

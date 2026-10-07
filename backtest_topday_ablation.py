from __future__ import annotations
import json,math
from pathlib import Path

def _returns(rows):
    out=[]
    for i in range(1,len(rows)):
        p,c=rows[i-1],rows[i]
        out.append({"date":c["date"],"r":(float(c["close"])/float(p["close"])-1.0)*float(p["leverage"])})
    return out

def compounded(rs):
    nav=1.0
    for r in rs: nav*=1.0+r
    return nav-1.0

def build(workbench="docs/workbench.json",out="docs/backtest_topday_ablation.json"):
    w=json.loads(Path(workbench).read_text());d=_returns(w.get("replay",{}).get("rows") or [])
    if len(d)<20:raise RuntimeError("TOPDAY_ABLATION_REPLAY_MISSING")
    base=compounded([x["r"] for x in d]);rank=sorted(range(len(d)),key=lambda i:d[i]["r"],reverse=True)
    cases=[]
    for n in (1,5,10,20):
        removed=set(rank[:n]);ret=compounded([x["r"] for i,x in enumerate(d) if i not in removed])
        cases.append({"removed_top_positive_sessions":n,"remaining_compounded_gross_return":ret,"delta_vs_full":ret-base,"removed_dates":[d[i]["date"] for i in rank[:n]]})
    x={"schema_version":1,"status":"PASS","full_compounded_gross_return":base,"cases":cases,"semantics":"Counterfactual diagnostic removing the strongest gross replay sessions. Not a tradable scenario, forecast, ranking or retuning rule.","automatic_promotion":False,"retuning_authorized":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

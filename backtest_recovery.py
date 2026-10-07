from __future__ import annotations
import json
from pathlib import Path
from publication_identity import identity
def build(workbench="docs/workbench.json",out="docs/backtest_recovery.json"):
    w=json.loads(Path(workbench).read_text());rows=w.get("replay",{}).get("rows") or []
    if len(rows)<20:raise RuntimeError("RECOVERY_REPLAY_MISSING")
    nav=peak=1.0;peak_i=0;episodes=[];active=None
    for i in range(1,len(rows)):
        p,c=rows[i-1],rows[i];nav*=1+(float(c["close"])/float(p["close"])-1)*float(p["leverage"])
        if nav>=peak:
            if active:
                active["recovery_date"]=c["date"];active["underwater_sessions"]=i-active["peak_index"];episodes.append(active);active=None
            peak=nav;peak_i=i
        else:
            dd=nav/peak-1
            if active is None:active={"peak_date":rows[peak_i]["date"],"peak_index":peak_i,"trough_date":c["date"],"max_drawdown":dd}
            elif dd<active["max_drawdown"]:active["max_drawdown"]=dd;active["trough_date"]=c["date"]
    if active:
        active["recovery_date"]=None;active["underwater_sessions"]=len(rows)-1-active["peak_index"];episodes.append(active)
    clean=[{k:v for k,v in e.items() if k!="peak_index"} for e in episodes]
    longest=max(clean,key=lambda x:x["underwater_sessions"],default=None);deepest=min(clean,key=lambda x:x["max_drawdown"],default=None)
    x={"schema_version":1,"publication_identity":identity(),"status":"PASS","episode_count":len(clean),"deepest_episode":deepest,"longest_episode":longest,"open_underwater_episode":clean[-1] if clean and clean[-1]["recovery_date"] is None else None,"episodes":clean,"semantics":"Gross frozen-replay underwater episodes measured in replay sessions. Recovery means prior NAV peak regained; no execution-parity claim.","automatic_promotion":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

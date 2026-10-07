from __future__ import annotations
import json
from pathlib import Path
from publication_identity import identity

def daily(rows):
    out=[]
    for i in range(1,len(rows)):
        p,c=rows[i-1],rows[i];out.append({"date":c["date"],"r":(float(c["close"])/float(p["close"])-1)*float(p["leverage"])})
    return out
def path_stats(xs):
    nav=peak=1.0;maxdd=0.0;peak_date=None;trough_date=None;cur_peak_date=None
    for x in xs:
        nav*=1+x["r"]
        if nav>=peak:peak=nav;cur_peak_date=x["date"]
        dd=nav/peak-1
        if dd<maxdd:maxdd=dd;peak_date=cur_peak_date;trough_date=x["date"]
    return {"compounded_gross_return":nav-1,"max_drawdown":maxdd,"max_drawdown_peak_date":peak_date,"max_drawdown_trough_date":trough_date}
def build(workbench="docs/workbench.json",out="docs/backtest_path_fragility.json"):
    w=json.loads(Path(workbench).read_text());d=daily(w.get("replay",{}).get("rows") or [])
    if len(d)<20:raise RuntimeError("PATH_FRAGILITY_REPLAY_MISSING")
    windows=[]
    for width in (21,63,126,252):
        if len(d)<width:continue
        vals=[]
        for i in range(len(d)-width+1):
            s=path_stats(d[i:i+width]);s.update({"start":d[i]["date"],"end":d[i+width-1]["date"]});vals.append(s)
        worst=min(vals,key=lambda x:x["compounded_gross_return"]);worstdd=min(vals,key=lambda x:x["max_drawdown"])
        windows.append({"sessions":width,"window_count":len(vals),"worst_return_window":worst,"worst_drawdown_window":worstdd})
    x={"schema_version":2,"publication_identity":identity(workbench),"status":"PASS","full_path":path_stats(d),"rolling_windows":windows,"semantics":"Chronological rolling path-risk diagnostic over frozen gross replay. Windows are exhaustive for fixed widths; no winner selection, retuning or future-performance inference.","automatic_promotion":False,"retuning_authorized":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

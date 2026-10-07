from __future__ import annotations
import json,statistics
from pathlib import Path
def build(workbench="docs/workbench.json",out="docs/backtest_transition_fragility.json"):
    w=json.loads(Path(workbench).read_text());rows=w.get("replay",{}).get("rows") or []
    if len(rows)<20:raise RuntimeError("TRANSITION_REPLAY_MISSING")
    sessions=[]
    for i in range(1,len(rows)):
        p,c=rows[i-1],rows[i];q=float(c["close"])/float(p["close"])-1;sr=q*float(p["leverage"]);changed=float(c["leverage"])!=float(p["leverage"])
        sessions.append({"date":c["date"],"strategy_gross_return":sr,"qqq_return":q,"transition":changed,"from_exposure":float(p["leverage"]),"to_exposure":float(c["leverage"])})
    tr=[x for x in sessions if x["transition"]];nt=[x for x in sessions if not x["transition"]]
    def stats(xs):
        return {"sessions":len(xs),"mean_strategy_gross_return":statistics.mean(x["strategy_gross_return"] for x in xs) if xs else None,"median_strategy_gross_return":statistics.median(x["strategy_gross_return"] for x in xs) if xs else None,"positive_share":sum(x["strategy_gross_return"]>0 for x in xs)/len(xs) if xs else None,"gross_return_sum":sum(x["strategy_gross_return"] for x in xs)}
    pairs={}
    for x in tr:
        k=f'{x["from_exposure"]:g}->{x["to_exposure"]:g}';pairs.setdefault(k,[]).append(x)
    x={"schema_version":1,"status":"PASS","transition_sessions":stats(tr),"non_transition_sessions":stats(nt),"transition_pairs":{k:stats(v) for k,v in sorted(pairs.items())},"transitions":tr,"semantics":"Descriptive attribution of frozen replay returns on sessions where target exposure changes versus sessions where it does not. It does not infer causality, alpha or execution parity.","retuning_authorized":False,"automatic_promotion":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from publication_identity import identity

def build(workbench="docs/workbench.json",out="docs/backtest_exposure_attribution.json"):
    w=json.loads(Path(workbench).read_text());rows=w.get("replay",{}).get("rows") or []
    if len(rows)<20:raise RuntimeError("EXPOSURE_ATTRIBUTION_REPLAY_MISSING")
    b=defaultdict(lambda:{"sessions":0,"qqq_return_sum":0.0,"gross_strategy_return_sum":0.0,"positive_gross_sum":0.0,"negative_gross_sum":0.0,"positive_sessions":0,"negative_sessions":0})
    for i in range(1,len(rows)):
        p,c=rows[i-1],rows[i];e=float(p["leverage"]);q=float(c["close"])/float(p["close"])-1;g=q*e;z=b[str(e)]
        z["sessions"]+=1;z["qqq_return_sum"]+=q;z["gross_strategy_return_sum"]+=g
        if g>0:z["positive_gross_sum"]+=g;z["positive_sessions"]+=1
        elif g<0:z["negative_gross_sum"]+=g;z["negative_sessions"]+=1
    total_pos=sum(z["positive_gross_sum"] for z in b.values());total_neg=sum(abs(z["negative_gross_sum"]) for z in b.values())
    for z in b.values():
        z["session_share"]=z["sessions"]/(len(rows)-1)
        z["positive_gross_share"]=z["positive_gross_sum"]/total_pos if total_pos else None
        z["negative_gross_magnitude_share"]=abs(z["negative_gross_sum"])/total_neg if total_neg else None
    x={"schema_version":1,"publication_identity":identity(),"status":"PASS","exposure_buckets":dict(sorted(b.items(),key=lambda kv:float(kv[0]))),"semantics":"Gross frozen-replay attribution by prior-session target exposure. Return sums are diagnostics, not compounded standalone sleeve returns or causal alpha.","automatic_promotion":False,"retuning_authorized":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

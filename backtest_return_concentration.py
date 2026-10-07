from __future__ import annotations
import json,statistics
from pathlib import Path

def _daily(rows):
    out=[]
    for i in range(1,len(rows)):
        p,c=rows[i-1],rows[i];q=float(c["close"])/float(p["close"])-1;exp=float(p["leverage"])
        out.append({"date":c["date"],"qqq_return":q,"exposure":exp,"gross_strategy_return":q*exp,"level":p.get("level"),"event":c.get("event")})
    return out

def build(workbench="docs/workbench.json",out="docs/backtest_return_concentration.json"):
    w=json.loads(Path(workbench).read_text());d=_daily(w.get("replay",{}).get("rows") or [])
    if len(d)<20:raise RuntimeError("RETURN_CONCENTRATION_REPLAY_MISSING")
    pos=sorted([x for x in d if x["gross_strategy_return"]>0],key=lambda x:x["gross_strategy_return"],reverse=True)
    total=sum(x["gross_strategy_return"] for x in pos)
    def share(n):return sum(x["gross_strategy_return"] for x in pos[:n])/total if total else None
    top10_dates=[x["date"] for x in pos[:10]]
    x={"schema_version":1,"status":"PASS","sessions":len(d),"positive_sessions":len(pos),"top1_positive_gross_return_share":share(1),"top5_positive_gross_return_share":share(5),"top10_positive_gross_return_share":share(10),"top20_positive_gross_return_share":share(20),"top10_session_dates":top10_dates,"median_daily_gross_return":statistics.median(x["gross_strategy_return"] for x in d),"semantics":"Concentration of summed positive daily gross replay returns. This is diagnostic, not additive compounded performance and not a promotion rule.","automatic_promotion":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

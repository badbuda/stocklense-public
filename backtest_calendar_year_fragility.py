from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
from publication_identity import identity

def _daily(rows):
    out=[]
    for i in range(1,len(rows)):
        p,c=rows[i-1],rows[i]
        out.append({"date":c["date"],"year":c["date"][:4],"r":(float(c["close"])/float(p["close"])-1)*float(p["leverage"])})
    return out
def compound(xs):
    n=1.0
    for x in xs:n*=1+x
    return n-1
def build(workbench="docs/workbench.json",out="docs/backtest_calendar_year_fragility.json"):
    w=json.loads(Path(workbench).read_text());d=_daily(w.get("replay",{}).get("rows") or [])
    if len(d)<20:raise RuntimeError("CALENDAR_YEAR_REPLAY_MISSING")
    by=defaultdict(list)
    for x in d:by[x["year"]].append(x["r"])
    years=[{"year":y,"sessions":len(v),"compounded_gross_return":compound(v)} for y,v in sorted(by.items())]
    full=compound([x["r"] for x in d]);loo=[]
    for y in sorted(by):
        r=compound([x["r"] for x in d if x["year"]!=y])
        loo.append({"excluded_year":y,"remaining_compounded_gross_return":r,"delta_vs_full":r-full})
    start=d[0]["date"];end=d[-1]["date"];full_years=sum(1 for z in years if z["sessions"]>=240);scope="MULTI_YEAR_DIAGNOSTIC" if full_years>=3 else "SHORT_REPLAY_ONLY";warning=None if full_years>=3 else "Fewer than 3 near-full trading years are present; leave-one-year-out is descriptive and not evidence of long-horizon robustness."
    x={"schema_version":2,"publication_identity":identity(),"status":"PASS","coverage":{"start":start,"end":end,"calendar_years":len(years),"near_full_years_240_sessions":full_years,"evidence_scope":scope,"warning":warning},"full_compounded_gross_return":full,"calendar_years":years,"leave_one_year_out":loo,"semantics":"Calendar-year attribution and leave-one-year-out fragility diagnostic. Years are not selected for optimization; no CAGR or alpha inference from partial years.","retuning_authorized":False,"automatic_promotion":False}
    Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

from __future__ import annotations
import csv,json
from collections import defaultdict
from pathlib import Path
from json_artifacts import write_json_atomic
def _f(x):
    try:return float(x)
    except:return None
def build_level_attribution(ledger_path="paper_portfolio/ledger.csv",out_path="shadow_history/level_attribution.json"):
    p=Path(ledger_path);rows=list(csv.DictReader(p.open())) if p.exists() else [];groups=defaultdict(list)
    prev=None
    for r in rows:
        eq=_f(r.get("equity"));level=r.get("target_level")
        ret=(eq/prev-1) if eq is not None and prev not in (None,0) else None
        if level and ret is not None:groups[level].append(ret)
        if eq is not None:prev=eq
    by={}
    for level,rets in sorted(groups.items()):
        compounded=1
        for x in rets:compounded*=1+x
        by[level]={"return_sessions":len(rets),"compounded_return":compounded-1,"average_daily_return":sum(rets)/len(rets),"positive_sessions":sum(x>0 for x in rets),"negative_sessions":sum(x<0 for x in rets)}
    result={"status":"ACTIVE" if len(rows)>=2 else "WAITING_FOR_RETURN_PATH","sessions":len(rows),"by_target_level":by,"method":"session equity returns attributed to target_level active for that ledger session; prospective only"}
    write_json_atomic(out_path,result);return result
if __name__=="__main__":print(json.dumps(build_level_attribution(),indent=2))

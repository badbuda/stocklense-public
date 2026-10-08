from __future__ import annotations
import csv,json
from pathlib import Path
def build_drawdown_budget(path="paper_portfolio/ledger.csv",out="shadow_history/drawdown_budget.json"):
    p=Path(path);rows=list(csv.DictReader(p.open())) if p.exists() else []
    r={"status":"WAITING_FOR_PROSPECTIVE_DATA","current_drawdown":None,"worst_drawdown":None,"distance_to_frozen_qc_maxdd":None,"qc_historical_max_drawdown":-.4969}
    if rows:
        d=[float(x["drawdown"]) for x in rows];cur=d[-1];worst=min(d);r.update(status="ACTIVE",current_drawdown=cur,worst_drawdown=worst,distance_to_frozen_qc_maxdd=cur-(-.4969))
    q=Path(out);q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build_drawdown_budget(),indent=2))

from __future__ import annotations
import csv,json
from pathlib import Path
def build_risk_telemetry(out="shadow_history/risk_telemetry.json"):
    p=Path("paper_portfolio/ledger.csv");rows=list(csv.DictReader(p.open())) if p.exists() else []
    if not rows:r={"status":"WAITING_FOR_PROSPECTIVE_DATA","sessions":0}
    else:
        lev=[float(x["target_leverage"]) for x in rows];dd=[float(x["drawdown"]) for x in rows]
        r={"status":"ACTIVE","sessions":len(rows),"current_leverage":lev[-1],"average_target_leverage":sum(lev)/len(lev),
           "max_observed_target_leverage":max(lev),"max_drawdown":min(dd),"current_drawdown":dd[-1],
           "sessions_at_3x":sum(x>=2.99 for x in lev),"sessions_at_2x":sum(1.99<=x<2.99 for x in lev),"sessions_below_2x":sum(x<1.99 for x in lev)}
    q=Path(out);q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build_risk_telemetry(),indent=2))

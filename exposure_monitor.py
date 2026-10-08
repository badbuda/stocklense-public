from __future__ import annotations
import csv,json
from pathlib import Path
def build_exposure(signal_path="shadow_history/latest.json",ledger_path="paper_portfolio/ledger.csv",out="shadow_history/exposure.json"):
    s=json.loads(Path(signal_path).read_text());x=s["latest"];p=Path(ledger_path);rows=list(csv.DictReader(p.open())) if p.exists() else []
    target={"qqq_weight":float(x["qqq_weight"]),"tqqq_weight":float(x["tqqq_weight"]),"cash_weight":1-float(x["qqq_weight"])-float(x["tqqq_weight"]),"effective_beta_proxy":float(x["qqq_weight"])+3*float(x["tqqq_weight"])}
    r={"target":target,"paper_status":"WAITING_FOR_FIRST_EXECUTION","drift":None,"rebalance_required":False}
    if rows:
        z=rows[-1];eq=float(z["equity"]);qw=float(z["qqq_shares"])*float(z["qqq_close"])/eq if eq else 0;tw=float(z["tqqq_shares"])*float(z["tqqq_close"])/eq if eq else 0
        drift={"qqq_weight":qw-target["qqq_weight"],"tqqq_weight":tw-target["tqqq_weight"],"max_abs_weight_drift":max(abs(qw-target["qqq_weight"]),abs(tw-target["tqqq_weight"]))}
        r.update(paper_status="ACTIVE",drift=drift,rebalance_required=drift["max_abs_weight_drift"]>.01)
    q=Path(out);q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build_exposure(),indent=2))

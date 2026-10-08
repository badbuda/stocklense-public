from __future__ import annotations
import csv,json
from pathlib import Path
from json_artifacts import write_json_atomic
from paper_execution_contract import as_dict as execution_contract, fingerprint as execution_contract_sha256
from stocklens.paper import FEE_BPS,SLIPPAGE_BPS
def build_execution_plan(signal_path="shadow_history/latest.json",ledger="paper_portfolio/ledger.csv",out="shadow_history/execution_plan.json"):
    s=json.loads(Path(signal_path).read_text());x=s["latest"];p=Path(ledger);rows=list(csv.DictReader(p.open())) if p.exists() else []
    last=rows[-1] if rows else None
    bootstrap=not rows
    action=s.get("action","UNKNOWN")
    required=bootstrap or action not in ("NO_CHANGE","UNKNOWN")
    r={"status":"PLAN_READY","signal_date":x["asof_date"],"signal_action":action,"bootstrap":bootstrap,"execution_required":required,
       "target":{"level":x["level"],"defense":x["defense_active"],"leverage":x["target_leverage"],"qqq_weight":x["qqq_weight"],"tqqq_weight":x["tqqq_weight"]},
       "prior_paper_session":last.get("session_date") if last else None,
       "policy":{"reductions":"09:31 ET reference open","additions":"09:32 ET reference open","fee_bps":FEE_BPS,"slippage_bps":SLIPPAGE_BPS,"whole_shares":True},
       "execution_contract_sha256":execution_contract_sha256(),"execution_contract":execution_contract(),
       "broker_orders_sent":False,"broker_authorized":False,"capital_scaling_authorized":False,
       "note":"Prospective paper execution plan only. No broker order is sent."}
    write_json_atomic(out,r);return r
if __name__=="__main__":print(json.dumps(build_execution_plan(),indent=2))

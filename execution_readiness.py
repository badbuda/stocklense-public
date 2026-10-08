from __future__ import annotations
import json
from pathlib import Path
from json_artifacts import write_json_atomic
def build(out="shadow_history/execution_readiness.json"):
    def j(p):q=Path(p);return json.loads(q.read_text()) if q.exists() else {}
    r=j("shadow_history/readiness.json");plan=j("shadow_history/execution_plan.json");audit=j("shadow_history/execution_audit.json")
    checks={"pipeline_ready":r.get("status")=="READY","plan_ready":plan.get("status")=="PLAN_READY","prior_execution_audit_clean":audit.get("status")=="PASS"}
    x={"status":"READY" if all(checks.values()) else "BLOCKED","checks":checks,"execution_required":bool(plan.get("execution_required")),"signal_date":plan.get("signal_date"),"broker_authorized":False,"capital_scaling_authorized":False,"note":"Readiness for prospective paper accounting only; never authorizes broker trading or capital scaling."}
    write_json_atomic(out,x);return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

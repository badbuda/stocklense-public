from __future__ import annotations
import json
from pathlib import Path
from golden_baseline_guard import validate_challenger

def audit(policy_path="research/GOLDEN_BASELINE_POLICY.json",workbench="docs/workbench.json"):
    problems=[]; checks=[]
    try:p=json.loads(Path(policy_path).read_text())
    except Exception:p={}
    try:w=json.loads(Path(workbench).read_text())
    except Exception:w={}
    expected={
      "status":"IMMUTABLE_GOLDEN_BASELINE",
      "overwrite_allowed":False,
      "automatic_promotion_allowed":False,
      "challengers_run_in_parallel":True,
      "frozen_contract_mutation_allowed":False,
    }
    observed={"status":p.get("status"),**{k:(p.get("policy") or {}).get(k) for k in expected if k!="status"}}
    for k,v in expected.items():
        ok=observed.get(k)==v;checks.append({"id":k,"expected":v,"observed":observed.get(k),"status":"PASS" if ok else "FAIL"})
        if not ok:problems.append(k)
    model_ok=w.get("model")=="StockLens 8.0 FROZEN"
    checks.append({"id":"workbench_model_frozen","expected":"StockLens 8.0 FROZEN","observed":w.get("model"),"status":"PASS" if model_ok else "FAIL"})
    if not model_ok:problems.append("workbench_model_frozen")
    return {"schema_version":1,"status":"PASS" if not problems else "BLOCKED","checks":checks,"problems":problems,
      "semantics":"Structural immutability guard only. PASS does not validate historical performance, future returns, or challenger superiority."}
def write(out="docs/baseline_immutability_audit.json"):
    x=audit();Path(out).write_text(json.dumps(x,indent=2)+"\n");return x
if __name__=="__main__":print(json.dumps(write(),indent=2))

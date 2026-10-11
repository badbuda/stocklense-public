from __future__ import annotations
import json
from pathlib import Path
from json_artifacts import write_json_atomic
def build_forward_quality(out="shadow_history/forward_quality.json"):
    def j(p):q=Path(p);return json.loads(q.read_text()) if q.exists() else {}
    path=j("shadow_history/forward_path.json");m=j("shadow_history/evidence_maturity.json");x=j("shadow_history/execution_quality.json")
    n=int(path.get("sessions",0) or 0)
    stage="NO_DATA" if n<2 else ("DESCRIPTIVE_ONLY" if n<20 else ("EARLY" if n<63 else ("FORMING" if n<252 else "MATURE")))
    r={"status":stage,"sessions":n,"performance_comparison_allowed":False,"risk_comparison_allowed":False,"strong_live_claims_allowed":False,"independently_qualified_frozen8_sessions":0,"legacy_row_count_not_a_verified_forward_claim":True,"execution_cost_observable":False,"modeled_execution_cost_diagnostic_available":x.get("status")=="ACTIVE","warning":"Prospective observations are descriptive; small samples are not evidence of durable edge." if n<63 else None}
    write_json_atomic(out,r);return r
if __name__=="__main__":print(json.dumps(build_forward_quality(),indent=2))

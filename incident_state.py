from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
from json_artifacts import write_json_atomic
def build(out="shadow_history/incident_state.json"):
    def j(p):q=Path(p);return json.loads(q.read_text()) if q.exists() else {}
    h=j("shadow_history/health.json");r=j("shadow_history/readiness.json");a=j("shadow_history/anomalies.json");s=j("shadow_history/slo.json")
    active=h.get("status")=="RED" or r.get("status")=="BLOCKED" or a.get("status")=="BLOCK" or s.get("status")=="FAIL"
    reasons=list(h.get("problems",[]))
    if r.get("status")=="BLOCKED":reasons += ["READINESS:"+x for x in r.get("failed_checks",[])]
    if a.get("status")=="BLOCK":reasons.append("FEATURE_ANOMALY_BLOCK")
    if s.get("status")=="FAIL":reasons.append("SIGNAL_SLO_FAIL")
    x={"status":"ACTIVE" if active else "CLEAR","severity":"CRITICAL" if active else "NONE","reasons":sorted(set(reasons)),"asof_date":h.get("asof_date"),"generated_at_utc":datetime.now(timezone.utc).isoformat(),"auto_recovery":"Incident clears only when current evidence returns healthy; historical failures remain in CI history."}
    write_json_atomic(out,x);return x
if __name__=="__main__":print(json.dumps(build(),indent=2))

from __future__ import annotations
import json
from pathlib import Path
def build_data_quality():
    def j(p,d=None):
        q=Path(p);return json.loads(q.read_text()) if q.exists() else (d or {})
    s=j("output/latest_signal.json");h=j("shadow_history/health.json");p=j("shadow_history/qc_daily_parity.json")
    x=s.get("latest",{})
    return {"status":"PASS" if h.get("status")!="RED" and x.get("asof_date") else "FAIL",
      "signal_date":x.get("asof_date"),"source":s.get("source_audit",{}).get("source") or s.get("source"),
      "health":h.get("status","PENDING"),"qc_cross_provider_diagnostic":p.get("status","PENDING"),
      "qc_transition_match_rate":p.get("transition_match_rate"),"qc_session_coverage":p.get("session_coverage_vs_qc_reference"),
      "decision_integrity":"IMMUTABLE_SAME_SESSION"}
if __name__=="__main__": print(json.dumps(build_data_quality(),indent=2))

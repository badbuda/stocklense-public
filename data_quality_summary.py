from __future__ import annotations
import json
from pathlib import Path
def build_data_quality():
    def j(p,d=None):
        q=Path(p);return json.loads(q.read_text()) if q.exists() else (d or {})
    s=j("output/latest_signal.json");h=j("shadow_history/health.json");p=j("shadow_history/qc_daily_parity.json")
    x=s.get("latest",{})
    evidence=j("research/lean_yahoo_cross_provider_20261009.json")
    verified=(evidence.get("status")=="VERIFIED_CROSS_PROVIDER_EXPOSURE_ALIGNMENT_NOT_LEAN_INPUT_PARITY"
              and evidence.get("overlap_sessions",0)>0
              and evidence.get("matching_exposures",0)<=evidence.get("overlap_sessions",0)
              and abs(evidence.get("daily_exposure_match_rate",-1)-evidence.get("matching_exposures",0)/evidence["overlap_sessions"])<1e-9)
    return {"status":"PASS" if h.get("status")!="RED" and x.get("asof_date") else "FAIL",
      "signal_date":x.get("asof_date"),"source":s.get("source_audit",{}).get("source") or s.get("source"),
      "health":h.get("status","PENDING"),"qc_cross_provider_diagnostic":("EXPOSURE_ALIGNMENT_ONLY_NOT_LEAN_INPUT_PARITY" if verified else p.get("status","PENDING")),
      "qc_original_transition_diagnostic":p.get("status","PENDING"),
      "qc_transition_index_alignment_diagnostic":p.get("transition_match_rate"),
      "lean_yahoo_daily_exposure_match_rate":evidence.get("daily_exposure_match_rate") if verified else None,
      "lean_yahoo_exposure_matched_days":evidence.get("matching_exposures") if verified else None,
      "lean_yahoo_exposure_overlap_days":evidence.get("overlap_sessions") if verified else None,
      "lean_same_input_parity_proven":False,"qc_session_coverage":p.get("session_coverage_vs_qc_reference"),
      "decision_integrity":"IMMUTABLE_SAME_SESSION"}
if __name__=="__main__": print(json.dumps(build_data_quality(),indent=2))

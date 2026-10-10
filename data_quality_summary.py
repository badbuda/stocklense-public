from __future__ import annotations
import json
import math
from pathlib import Path
def build_data_quality():
    def j(p,d=None):
        q=Path(p);return json.loads(q.read_text()) if q.exists() else (d or {})
    s=j("output/latest_signal.json");h=j("shadow_history/health.json");p=j("shadow_history/qc_daily_parity.json")
    x=s.get("latest",{})
    # A few basis points of vendor SMA adjustment can flip a 1%-buffer transition.
    f=x.get("features",{}) if isinstance(x.get("features"),dict) else {}
    try:
        close=float(f["close"])
        sma200=float(f["sma200"])
        margin_bps=10000*(close/(1.01*sma200)-1) if (
            math.isfinite(close) and math.isfinite(sma200) and close>0 and sma200>0
        ) else None
    except (ValueError,TypeError,KeyError,ZeroDivisionError):
        margin_bps=None
    near_threshold=margin_bps is not None and abs(margin_bps)<10.0
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
      "sma200_upper_hysteresis_margin_bps":margin_bps,
      "sma200_upper_threshold_within_10bps":near_threshold if margin_bps is not None else None,
      "sma200_threshold_diagnostic":("SOURCE_SENSITIVE_WITHIN_10BPS" if near_threshold
          else "NOT_NEAR_UPPER_THRESHOLD" if margin_bps is not None else "INSUFFICIENT_FEATURES"),
      "sma200_threshold_data_source":"QQQ_ADJUSTED_SIGNAL_VENDOR_NOT_LEAN_PARITY",
      "decision_integrity":"IMMUTABLE_SAME_SESSION"}
if __name__=="__main__": print(json.dumps(build_data_quality(),indent=2))

from __future__ import annotations
import json
from pathlib import Path
from json_artifacts import write_json_atomic

def build_readiness(out_path="shadow_history/readiness.json"):
    def load(path, default=None):
        p=Path(path);return json.loads(p.read_text()) if p.exists() else (default or {})
    signal=load("output/latest_signal.json");health=load("shadow_history/health.json")
    replay=load("historical_replay/summary.json");anomaly=load("shadow_history/anomalies.json",{"status":"MISSING"})
    integrity=load("shadow_history/artifact_integrity.json",{"status":"PENDING"})
    latest=signal.get("latest",{})
    checks={
        "signal_present":bool(latest.get("asof_date")),
        "pipeline_healthy":health.get("status") in ("GREEN","PASS"),
        "signal_matches_replay":bool(latest.get("asof_date")) and latest.get("asof_date")==replay.get("last_date"),
        "qc_reference_locked":Path("governance/qc_724_daily_state_manifest.json").exists(),
        "paper_engine_initialized":Path("paper_portfolio/ledger.csv").exists(),
        "anomaly_clear":anomaly.get("status")=="CLEAR",
        "artifact_integrity":integrity.get("status")=="PASS",
    }
    required=("signal_present","pipeline_healthy","signal_matches_replay","qc_reference_locked","anomaly_clear")
    failed_checks=[k for k in required if not checks[k]]
    ready=not failed_checks
    action=signal.get("action","UNKNOWN")
    result={
        "status":"READY" if ready else "BLOCKED","checks":checks,"failed_checks":failed_checks,
        "scope":"SHADOW_SIGNAL_PIPELINE_ONLY","capital_deployment_ready":False,
        "broker_execution_ready":False,"readiness_label":"SHADOW_SIGNAL_READY_NOT_LIVE" if ready else "SHADOW_PIPELINE_BLOCKED",
        "health_status":health.get("status","MISSING"),"anomaly_status":anomaly.get("status","MISSING"),
        "artifact_integrity_status":integrity.get("status","PENDING"),
        "integrity_evidence_phase":"POST_READINESS_VALIDATION",
        "signal_date":latest.get("asof_date"),"action":action,
        "execution_required":ready and action not in ("NO_CHANGE","UNKNOWN"),
        "execution_note":"No exposure change required." if action=="NO_CHANGE" else ("Validated state change requires paper reconciliation." if ready else "Execution blocked until readiness checks pass."),
        "observational_only":True,
    }
    write_json_atomic(out_path,result);return result

if __name__=="__main__":print(json.dumps(build_readiness(),indent=2))

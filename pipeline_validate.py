from __future__ import annotations
import csv, json, sys
from pathlib import Path

def validate():
    errors=[]
    hp=Path("historical_replay/summary.json"); dp=Path("historical_replay/daily_states.csv")
    if not hp.exists() or not dp.exists(): errors.append("MISSING_HISTORICAL_REPLAY")
    else:
        h=json.loads(hp.read_text())
        rows=list(csv.DictReader(dp.open(encoding="utf-8",newline="")))
        if h.get("kind")!="HISTORICAL_REPLAY_NOT_PROSPECTIVE": errors.append("REPLAY_GOVERNANCE_LABEL_MISSING")
        if h.get("sessions")!=len(rows): errors.append("REPLAY_SESSION_COUNT_MISMATCH")
        if rows and rows[-1]["asof_date"]!=h.get("last_date"): errors.append("REPLAY_LAST_DATE_MISMATCH")
        if len({r["asof_date"] for r in rows})!=len(rows): errors.append("REPLAY_DUPLICATE_SESSION")
    health=Path("shadow_history/health.json")
    if health.exists():
        x=json.loads(health.read_text())
        if x.get("status")=="RED": errors.append("HEALTH_RED")
    latest=Path("shadow_history/latest.json")
    if latest.exists() and hp.exists():
        s=json.loads(latest.read_text()).get("latest",{}).get("asof_date")
        r=json.loads(hp.read_text()).get("last_date")
        if s and r and s!=r: errors.append("STALE_SIGNAL_VS_REPLAY")
    perf=Path("shadow_history/performance.json")
    if not perf.exists(): errors.append("MISSING_PERFORMANCE_ANALYTICS")
    journal=Path("shadow_history/decision_journal.csv")
    if not journal.exists(): errors.append("MISSING_DECISION_JOURNAL")
    for required in ("shadow_history/readiness.json","shadow_history/daily_digest.json","shadow_history/slo.json","shadow_history/regime_analytics.json","shadow_history/change_digest.json","shadow_history/stress_scenarios.json","shadow_history/exposure.json","shadow_history/drawdown_budget.json","shadow_history/anomalies.json","shadow_history/recovery_plan.json","shadow_history/data_provenance.json","shadow_history/qc_input_ingestion.json","shadow_history/qc_same_input_parity.json","shadow_history/qc_parity_dossier.json","shadow_history/execution_plan.json","shadow_history/trade_receipts.json","shadow_history/execution_audit.json","shadow_history/cost_attribution.json","shadow_history/execution_readiness.json","shadow_history/incident_state.json","shadow_history/dependency_integrity.json","shadow_history/artifact_catalog.json","shadow_history/run_manifest.json","shadow_history/artifact_integrity.json","research/prospective/registry.json","docs/prospective_maturity.json","docs/capital_readiness.json","output/research_provenance.json"):
        if not Path(required).exists(): errors.append("MISSING_"+Path(required).stem.upper())
    maturity=Path("docs/prospective_maturity.json")
    if maturity.exists():
        mx=json.loads(maturity.read_text())
        if mx.get("status")!="PASS": errors.append("PROSPECTIVE_MATURITY_BLOCKED")
        if mx.get("producer_current") is not True: errors.append("PROSPECTIVE_PRODUCER_STALE")
        if any(row.get("definition_current") is not True for row in mx.get("experiments",[])): errors.append("PROSPECTIVE_DEFINITION_DRIFT")
    capital=Path("docs/capital_readiness.json")
    if capital.exists():
        cx=json.loads(capital.read_text())
        if cx.get("automatic_trading_authorized") is not False or cx.get("scaled_capital_ready") is not False or cx.get("observational_only") is not True:
            errors.append("CAPITAL_READINESS_GOVERNANCE_INVALID")
    integrity=Path("shadow_history/artifact_integrity.json")
    if integrity.exists() and json.loads(integrity.read_text()).get("status")!="PASS": errors.append("ARTIFACT_INTEGRITY_FAIL")
    anomaly=Path("shadow_history/anomalies.json")
    if anomaly.exists() and json.loads(anomaly.read_text()).get("status")=="BLOCK": errors.append("FEATURE_ANOMALY_BLOCK")
    readiness=Path("shadow_history/readiness.json")
    if readiness.exists() and json.loads(readiness.read_text()).get("status")!="READY": errors.append("READINESS_BLOCKED")
    slo=Path("shadow_history/slo.json")
    if slo.exists() and json.loads(slo.read_text()).get("status")=="FAIL": errors.append("SLO_FAIL")
    result={"status":"PASS" if not errors else "FAIL","errors":errors}
    Path("shadow_history/pipeline_validation.json").write_text(json.dumps(result,indent=2)+"\n")
    if errors: raise SystemExit("PIPELINE_VALIDATION_FAIL:"+",".join(errors))
    return result
if __name__=="__main__": print(json.dumps(validate(),indent=2))

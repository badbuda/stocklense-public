from __future__ import annotations
import json
from pathlib import Path
from publication_identity import identity as publication_identity
from prospective_gate import GATE as PROSPECTIVE_GATE
EXECUTION_OBSERVATION_MIN_PROSPECTIVE_SESSIONS=5
EXTENDED_EVIDENCE_MIN_SESSIONS=20

def load(path,default=None):
 try:return json.loads(Path(path).read_text())
 except Exception:return {} if default is None else default

def build(out="docs/capital_readiness.json"):
 reg=load("research/prospective/registry.json")
 health=load("docs/workbench_evidence_health.json")
 exe=load("shadow_history/execution_readiness.json")
 smoke=load("docs/simulator_smoke.json")
 maturity=load("docs/prospective_maturity.json")
 pub=publication_identity()
 audits=reg.get("last_ingestion_audit",[])
 target_audit=next((x for x in audits if x.get("experiment_id")=="SL9-007-UPSHIFT-CONFIRMATION"),{})
 accepted_raw=target_audit.get("accepted_completed_xnys_rows")
 prospective_raw=target_audit.get("persisted_prospective_rows")
 source_available=target_audit.get("source_status")=="AVAILABLE"
 definition_current=target_audit.get("definition_matches_registration") is True
 evidence_fingerprint_current=target_audit.get("fingerprint_matches_registration") is True
 audit_schema_complete=source_available and definition_current and accepted_raw is not None and prospective_raw is not None
 accepted=int(accepted_raw or 0)
 prospective=int(prospective_raw or 0)
 persistence_consistent=audit_schema_complete and prospective==accepted
 prospective_gate_ok=audit_schema_complete and target_audit.get("gate")==PROSPECTIVE_GATE
 checks={
  "evidence_health_healthy":health.get("status")=="HEALTHY",
  "market_session_current":health.get("market_session_freshness")=="CURRENT",
  "signal_replay_aligned":health.get("market_session",{}).get("signal_replay_aligned") is True,
  "paper_execution_ready":exe.get("status")=="READY",
  "simulator_accounting_pass":smoke.get("accounting_invariants",{}).get("status")=="PASS",
  "simulator_provenance_present":bool(smoke.get("replay_dataset_sha256") and smoke.get("contract_sha256") and smoke.get("replay_rows_sha256")),
  "simulator_dataset_matches":smoke.get("replay_dataset_sha256")==pub.get("replay_dataset_sha256"),
  "simulator_rows_match":smoke.get("replay_rows_sha256")==pub.get("replay_rows_sha256"),
  "simulator_contract_matches":smoke.get("contract_sha256")==pub.get("simulator_contract_sha256"),
  "simulator_generation_matches":smoke.get("publication_identity",{}).get("generation_id")==pub.get("generation_id"),
  "automatic_model_change_disabled":health.get("automatic_model_change") is False,
  "automatic_promotion_disabled":health.get("automatic_promotion") is False,
  "prospective_maturity_pass":maturity.get("status")=="PASS",
  "prospective_producer_current":maturity.get("producer_current") is True,
  "prospective_producer_git_matches_publication":maturity.get("producer_git_sha")==pub.get("git_sha"),
  "prospective_source_available":source_available,
  "prospective_definition_current":definition_current,
  "prospective_audit_schema_complete":audit_schema_complete,
  "prospective_ingestion_gate_valid":prospective_gate_ok,
  "prospective_persistence_consistent":persistence_consistent,
 }
 technical=all(checks.values())
 pilot=technical and prospective>=EXECUTION_OBSERVATION_MIN_PROSPECTIVE_SESSIONS
 extended=technical and prospective>=EXTENDED_EVIDENCE_MIN_SESSIONS
 stage="SHADOW_ONLY"
 if pilot: stage="LIMITED_EXECUTION_OBSERVATION_ELIGIBLE"
 if extended: stage="PROSPECTIVE_EVIDENCE_BUILDING"
 result={
  "schema_version":2,"publication_identity":pub,"stage":stage,"prospective_completed_sessions":prospective,
  "prospective_evidence":{"definition_current":definition_current,"registered_definition_fingerprint":target_audit.get("registered_definition_fingerprint"),"current_definition_fingerprint":target_audit.get("current_definition_fingerprint"),"evidence_fingerprint_current":evidence_fingerprint_current,"registered_fingerprint":target_audit.get("registered_fingerprint"),"queue_fingerprint":target_audit.get("queue_fingerprint"),"source_status":target_audit.get("source_status","MISSING_AUDIT"),"returns_csv":target_audit.get("returns_csv"),"producer_current":maturity.get("producer_current"),"producer_git_sha":maturity.get("producer_git_sha"),"registry_updated_at_utc":maturity.get("registry_updated_at_utc"),"maturity_status":maturity.get("status","MISSING"),"experiment_id":"SL9-007-UPSHIFT-CONFIRMATION","accepted_completed_xnys_rows":accepted_raw,"persisted_prospective_rows":prospective_raw,"audit_schema_complete":audit_schema_complete,"persistence_consistent":persistence_consistent,"gate":target_audit.get("gate"),"strict_gate_valid":prospective_gate_ok},
  "thresholds":{"limited_execution_observation":EXECUTION_OBSERVATION_MIN_PROSPECTIVE_SESSIONS,"extended_prospective_evidence":EXTENDED_EVIDENCE_MIN_SESSIONS},
  "checks":checks,"technical_checks_pass":technical,
  "limited_execution_observation_eligible":pilot,"extended_prospective_evidence_threshold_met":extended,
  "scaled_capital_ready":False,
  "scaled_capital_policy":"NEVER_AUTOMATIC. Requires explicit human review of prospective evidence, execution behavior, drawdowns, costs and unresolved evidence limitations.",
  "full_lean_execution_parity":False,
  "automatic_trading_authorized":False,"observational_only":True,"semantics":"Evidence-readiness classification only. LIMITED_EXECUTION_OBSERVATION_ELIGIBLE means the system has enough prospective sessions to begin observing tiny/manual execution behavior if a human independently chooses to do so; it is not an investment recommendation, allocation decision, broker authorization, or evidence that scaled capital is ready.",
  "next_blockers":[k for k,v in checks.items() if not v]+([] if prospective>=EXECUTION_OBSERVATION_MIN_PROSPECTIVE_SESSIONS else [f"prospective_sessions_{prospective}_of_{EXECUTION_OBSERVATION_MIN_PROSPECTIVE_SESSIONS}_for_execution_observation"]),
 }
 Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_text(json.dumps(result,indent=2)+"\n")
 return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

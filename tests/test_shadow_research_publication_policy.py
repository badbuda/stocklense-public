"""Research attention may not break a safe shadow signal, but is NEVER capital proof."""
import json
from pathlib import Path

import pytest

from shadow_research_publication_policy import disposition
from pipeline_validate import validate


def maturity(status="ATTENTION"):
    sha = "a"*40
    record = {
        "experiment_id": "SL9-007-UPSHIFT-CONFIRMATION",
        "status": "ACTIVE_RESEARCH_ONLY",
        "automatic_promotion": False,
        "definition_current": True,
        "audit_schema_complete": True,
        "persistence_consistent": True,
        "zero_backfill_enforced": True,
        "source_status": "AVAILABLE",
        "evidence_state": "ATTENTION_PROSPECTIVE_EVIDENCE_FINGERPRINT_DRIFT",
        "evidence_fingerprint_current": False,
        "evidence_fingerprint_audited": True,
        "source_fingerprint_review_required": True,
        "registered_fingerprint": "1"*64,
        "queue_fingerprint": "2"*64,
    }
    return {
        "schema_version": 6,
        "producer_git_sha": sha,
        "current_git_sha": sha,
        "producer_current": True,
        "status": status,
        "experiments": [record],
    }


def test_audited_fingerprint_drift_allows_shadow_publication_not_maturity_pass():
    report = maturity()
    allowed, label = disposition(report)
    assert allowed
    assert label == "RESEARCH_DRIFT_RECORDED_SHADOW_PUBLICATION_ONLY"
    assert report["status"] == "ATTENTION"
    assert report["experiments"][0]["source_fingerprint_review_required"]
    assert report["experiments"][0]["automatic_promotion"] is False


@pytest.mark.parametrize("field,value", [
    ("status", "BLOCKED"),
    ("status", "UNEXPECTED"),
    ("producer_current", False),
    ("schema_version", 5),
    ("experiments", []),
])
def test_bad_global_maturity_blocks(field, value):
    report = maturity()
    report[field] = value
    assert disposition(report)[0] is False


@pytest.mark.parametrize("field,value", [
    ("status", "PROMOTED"),
    ("automatic_promotion", True),
    ("definition_current", False),
    ("persistence_consistent", False),
    ("audit_schema_complete", False),
    ("zero_backfill_enforced", False),
    ("source_status", "MISSING_RETURNS_SOURCE"),
    ("evidence_state", "BLOCKED_PERSISTENCE_MISMATCH"),
    ("evidence_fingerprint_audited", False),
    ("evidence_fingerprint_current", True),
    ("source_fingerprint_review_required", False),
    ("registered_fingerprint", "forged"),
    ("queue_fingerprint", "1"*64),
])
def test_mutation_or_unknown_research_attention_cannot_publish(field, value):
    report = maturity()
    report["experiments"][0][field] = value
    assert disposition(report)[0] is False


def test_missing_or_duplicate_experiments_never_pass():
    report=maturity()
    report["experiments"] = [report["experiments"][0]]*2
    assert disposition(report)[0] is False


def test_valid_research_pass_also_allows_shadow_publication():
    report=maturity(status="PASS")
    row=report["experiments"][0]
    row.update({
        "evidence_state":"ACCUMULATING_FORWARD_EVIDENCE",
        "evidence_fingerprint_current":True,
        "source_fingerprint_review_required":False,
    })
    assert disposition(report)==(True,"RESEARCH_PASS_SHADOW_ONLY")


REQUIRED = (
    "shadow_history/readiness.json",
    "shadow_history/daily_digest.json",
    "shadow_history/slo.json",
    "shadow_history/regime_analytics.json",
    "shadow_history/change_digest.json",
    "shadow_history/stress_scenarios.json",
    "shadow_history/exposure.json",
    "shadow_history/drawdown_budget.json",
    "shadow_history/anomalies.json",
    "shadow_history/recovery_plan.json",
    "shadow_history/data_provenance.json",
    "shadow_history/qc_input_ingestion.json",
    "shadow_history/qc_same_input_parity.json",
    "shadow_history/qc_parity_dossier.json",
    "shadow_history/execution_plan.json",
    "shadow_history/trade_receipts.json",
    "shadow_history/execution_audit.json",
    "shadow_history/cost_attribution.json",
    "shadow_history/execution_readiness.json",
    "shadow_history/incident_state.json",
    "shadow_history/dependency_integrity.json",
    "shadow_history/artifact_catalog.json",
    "shadow_history/run_manifest.json",
    "shadow_history/artifact_integrity.json",
    "research/prospective/registry.json",
    "docs/prospective_maturity.json",
    "docs/capital_readiness.json",
    "output/research_provenance.json",
)


def write(path, payload):
    p=Path(path)
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(payload))


def setup_complete_pipeline(tmp_path, monkeypatch, research=None):
    monkeypatch.chdir(tmp_path)
    for path in REQUIRED:
        write(path, {})
    write("historical_replay/summary.json",{
        "kind":"HISTORICAL_REPLAY_NOT_PROSPECTIVE",
        "sessions":1,"last_date":"2026-10-26",
    })
    Path("historical_replay/daily_states.csv").write_text("asof_date\\n2026-10-26\\n".replace("\\n","\n"))
    write("shadow_history/latest.json",{"latest":{"asof_date":"2026-10-26"}})
    write("shadow_history/health.json",{"status":"GREEN"})
    write("shadow_history/performance.json",{})
    Path("shadow_history/decision_journal.csv").write_text("asof_date\n")
    write("shadow_history/readiness.json",{"status":"READY"})
    write("shadow_history/slo.json",{"status":"PASS"})
    write("shadow_history/artifact_integrity.json",{"status":"PASS"})
    write("shadow_history/anomalies.json",{"status":"CLEAR"})
    write("docs/capital_readiness.json",{
        "automatic_trading_authorized":False,
        "scaled_capital_ready":False,
        "observational_only":True,
    })
    write("docs/prospective_maturity.json",research or maturity())


def test_full_pipeline_marks_attention_unresolved_but_allows_safe_shadow(tmp_path, monkeypatch):
    setup_complete_pipeline(tmp_path, monkeypatch)
    result = validate()
    assert result["status"] == "PASS"
    assert result["errors"] == []
    assert result["research_maturity_status"] == "ATTENTION"
    assert result["research_publication_disposition"] == "RESEARCH_DRIFT_RECORDED_SHADOW_PUBLICATION_ONLY"
    assert result["automatic_trading_authorized"] is False
    assert result["automatic_model_promotion"] is False
    assert json.loads(Path("docs/prospective_maturity.json").read_text())["status"] == "ATTENTION"


def test_full_pipeline_still_fails_closed_on_unreviewed_research(tmp_path, monkeypatch):
    report=maturity()
    report["experiments"][0]["persistence_consistent"]=False
    setup_complete_pipeline(tmp_path, monkeypatch, research=report)
    with pytest.raises(SystemExit, match="PROSPECTIVE_MATURITY_BLOCKED"):
        validate()
    assert json.loads(Path("shadow_history/pipeline_validation.json").read_text())["status"]=="FAIL"


def test_full_pipeline_never_permits_capital_authorization(tmp_path, monkeypatch):
    setup_complete_pipeline(tmp_path, monkeypatch)
    write("docs/capital_readiness.json",{
        "automatic_trading_authorized":True,
        "scaled_capital_ready":True,
        "observational_only":False,
    })
    with pytest.raises(SystemExit, match="CAPITAL_READINESS_GOVERNANCE_INVALID"):
        validate()

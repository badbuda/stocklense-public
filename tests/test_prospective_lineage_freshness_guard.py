import json
from pathlib import Path
from prospective_freshness import audit


def _setup(tmp_path,monkeypatch,*,definition=True,evidence=True,rows=2):
    monkeypatch.chdir(tmp_path)
    Path("research/prospective").mkdir(parents=True)
    Path("docs").mkdir()
    Path("research/prospective/registry.json").write_text(json.dumps({
        "candidates":[{"experiment_id":"test","inception_date":"2026-09-26"}],
        "last_ingestion_audit":[{"experiment_id":"test",
           "accepted_completed_xnys_rows":rows,
           "persisted_prospective_rows":rows,
           "definition_matches_registration":definition,
           "fingerprint_matches_registration":evidence}]
    }))
    Path("docs/data.json").write_text(json.dumps({"data_provenance":{
        "last_completed_date":"2026-10-09","status":"COMPLETE"}}))
    Path("docs/workbench.json").write_text(json.dumps({
        "publication":{"signal_asof":"2026-10-09"}}))
    return audit("research/prospective/registry.json","docs/workbench.json","docs/data.json")


def test_matched_lineage_can_be_current(tmp_path,monkeypatch):
    r=_setup(tmp_path,monkeypatch)
    assert r["experiments"][0]["status"]=="CURRENT"
    assert r["status"]=="PASS"


def test_evidence_drift_requires_review_not_current(tmp_path,monkeypatch):
    r=_setup(tmp_path,monkeypatch,evidence=False)
    assert r["experiments"][0]["status"]=="ATTENTION_PROSPECTIVE_EVIDENCE_FINGERPRINT_DRIFT"
    assert r["status"]=="ATTENTION"
    assert r["experiments"][0]["definition_matches_registration"] is True


def test_definition_change_blocks_forward_confidence(tmp_path,monkeypatch):
    r=_setup(tmp_path,monkeypatch,definition=False)
    assert r["experiments"][0]["status"]=="BLOCKED_PROSPECTIVE_DEFINITION_MISMATCH"
    assert r["status"]=="BLOCKED"


def test_missing_audit_proof_fails_closed(tmp_path,monkeypatch):
    r=_setup(tmp_path,monkeypatch)
    data=json.loads(Path("research/prospective/registry.json").read_text())
    del data["last_ingestion_audit"][0]["fingerprint_matches_registration"]
    Path("research/prospective/registry.json").write_text(json.dumps(data))
    r=audit("research/prospective/registry.json","docs/workbench.json","docs/data.json")
    assert r["status"]=="ATTENTION"

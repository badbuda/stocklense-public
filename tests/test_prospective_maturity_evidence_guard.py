"""Regression contract: no apparent forward maturity when registered evidence changes."""
import json
from pathlib import Path

from prospective_maturity import build
from prospective_gate import GATE


def fixture(tmp_path, monkeypatch, *, same=True, defn=True, evidence_key=True,
            accepted=10, persisted=10):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    Path("research/prospective").mkdir(parents=True)
    x={"experiment_id":"SL9-007-UPSHIFT-CONFIRMATION",
       "source_status":"AVAILABLE",
       "accepted_completed_xnys_rows":accepted,
       "persisted_prospective_rows":persisted,
       "definition_matches_registration":defn,
       "fingerprint_matches_registration":same,
       "gate":GATE}
    if not evidence_key:
        del x["fingerprint_matches_registration"]
    registry={"schema_version":1,"producer_git_sha":"a"*40,
              "ingestion_gate":GATE,
              "candidates":[{"experiment_id":x["experiment_id"],
                             "status":"ACTIVE_RESEARCH_ONLY",
                             "inception_date":"2026-09-26"}],
              "last_ingestion_audit":[x]}
    p=Path("research/prospective/registry.json")
    p.write_text(json.dumps(registry))
    return build(str(p), "research/prospective/maturity-result.json")


def test_matched_complete_forward_ledger_is_accumulating_not_promoted(tmp_path, monkeypatch):
    x=fixture(tmp_path,monkeypatch)
    assert x["status"] == "PASS"
    z=x["experiments"][0]
    assert z["evidence_state"] == "ACCUMULATING_FORWARD_EVIDENCE"
    assert z["evidence_fingerprint_current"] is True
    assert z["source_fingerprint_review_required"] is False


def test_unchanged_definition_does_not_hide_changed_evidence(tmp_path,monkeypatch):
    x=fixture(tmp_path,monkeypatch,same=False)
    assert x["status"] == "ATTENTION"
    z=x["experiments"][0]
    assert z["definition_current"] is True
    assert z["persistence_consistent"] is True
    assert z["source_fingerprint_review_required"] is True
    assert z["evidence_state"] == "ATTENTION_PROSPECTIVE_EVIDENCE_FINGERPRINT_DRIFT"


def test_changed_definition_or_missing_evidence_audit_blocks(tmp_path,monkeypatch):
    assert fixture(tmp_path,monkeypatch,defn=False)["status"]=="BLOCKED"
    assert fixture(tmp_path,monkeypatch,evidence_key=False)["status"]=="BLOCKED"


def test_unreconciled_row_counts_block_even_if_fingerprints_match(tmp_path,monkeypatch):
    x=fixture(tmp_path,monkeypatch,accepted=10,persisted=9)
    assert x["status"]=="BLOCKED"
    assert x["experiments"][0]["evidence_state"]=="BLOCKED_PERSISTENCE_MISMATCH"


def test_no_prospective_sessions_is_not_successful_sample(tmp_path,monkeypatch):
    x=fixture(tmp_path,monkeypatch,accepted=0,persisted=0)
    assert x["experiments"][0]["evidence_state"]=="WAITING_FOR_POST_INCEPTION_COMPLETED_XNYS"
    assert not x["experiments"][0]["source_fingerprint_review_required"]

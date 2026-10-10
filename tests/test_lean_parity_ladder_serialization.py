"""Regression: a blocked LEAN evidence ladder is parseable and cannot imply capital readiness."""
import json
from pathlib import Path

from lean_parity_evidence_ladder import build


def test_absent_private_original_features_emit_valid_json_and_unproven_layers(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("shadow_history").mkdir()
    Path("research").mkdir()
    saved=Path("research/native_evidence_ladder.json")
    data=build(out=saved)
    persisted=json.loads(saved.read_text())
    assert persisted==data
    assert saved.read_bytes().endswith(b"\n")
    assert data["status"]=="EVIDENCE_INCOMPLETE"
    assert data["frozen_model_mutated"] is False
    assert all(not layer["proven"] for layer in data["layers"])


def test_same_input_claim_is_not_a_substitute_for_independent_portfolio_path(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("shadow_history").mkdir()
    Path("research").mkdir()
    Path("shadow_history/qc_same_input_parity.json").write_text(json.dumps({
        "same_input_parity_proven":True,"same_input_state_match":True
    }))
    saved=Path("research/native_evidence_ladder.json")
    data=build(out=saved)
    assert data["status"]=="EVIDENCE_INCOMPLETE"
    assert data["layers"][1]["proven"] is True
    assert data["layers"][2]["proven"] is False
    assert data["layers"][3]["proven"] is False

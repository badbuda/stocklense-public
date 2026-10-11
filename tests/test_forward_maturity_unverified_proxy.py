import json
from datetime import date
from pathlib import Path
import pytest
import evidence_maturity
import forward_quality
from frozen_forward_evidence_contract import build_record


def test_500_legacy_paper_rows_never_create_live_proof(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("shadow_history").mkdir()
    Path("shadow_history/forward_path.json").write_text(json.dumps({"sessions":500}))
    Path("shadow_history/execution_quality.json").write_text(json.dumps({"status":"ACTIVE"}))
    result=forward_quality.build_forward_quality()
    assert result["sessions"] == 500
    assert result["strong_live_claims_allowed"] is False
    assert result["performance_comparison_allowed"] is False
    assert result["risk_comparison_allowed"] is False
    assert result["independently_qualified_frozen8_sessions"] == 0
    assert result["execution_cost_observable"] is False


def test_500_legacy_challenger_rows_never_pass_maturity(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("shadow_history").mkdir()
    monkeypatch.setattr(evidence_maturity, "gated_ledger_rows",
        lambda: ([{"session_date":"2026-09-29"}]*500, [], date(2026,9,26)))
    r=evidence_maturity.build_evidence_maturity()
    assert r["prospective_sessions"] == 500
    assert r["strong_live_claims_allowed"] is False
    assert r["performance_interpretation_allowed"] is False
    assert r["independently_qualified_frozen8_sessions"] == 0


def test_local_record_cannot_claim_capital_or_external_attestation():
    for field in ("capital_authorized","independently_qualified_forward",
                  "live_broker_trading_authorized","model_automatically_promoted"):
        row={"schema_version":1,"model":"STOCKLENS_8_0_FROZEN",
             "session_date":"2026-10-09","status":"MISSED",
             "broker_orders_authorized":False,"missing_reason":"no_capture",
             "external_server_receipt":None,"market_source":None,field:True}
        with pytest.raises(ValueError,match="FORWARD_LOCAL_RECORD_CANNOT_AUTHORIZE"):
            build_record(row)

"""No 20/63/252 row count proves qualified frozen8 ETF paper, alpha or broker fill."""
import json
from pathlib import Path
import evidence_maturity
from forward_quality import build_forward_quality

def test_252_unverified_rows_cannot_justify_strong_claims(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(evidence_maturity,"gated_ledger_rows",
        lambda: ([{"asof_date":"2026-10-09"}]*252,[],
                 __import__("datetime").date(2026,9,26)))
    Path("shadow_history").mkdir()
    x=evidence_maturity.build_evidence_maturity("shadow_history/evidence_maturity.json")
    assert x["prospective_sessions"]==252
    assert x["stage"]=="ROW_COUNT_252_UNQUALIFIED"
    assert x["strong_live_claims_allowed"] is False
    assert x["performance_interpretation_allowed"] is False
    assert x["independently_qualified_frozen8_sessions"]==0

def test_false_forward_claims_at_252_with_modeled_execution(tmp_path,monkeypatch):
    monkeypatch.chdir(tmp_path)
    Path("shadow_history").mkdir()
    Path("shadow_history/forward_path.json").write_text(json.dumps({"sessions":252}))
    Path("shadow_history/execution_quality.json").write_text(json.dumps({"status":"ACTIVE"}))
    x=build_forward_quality("shadow_history/forward_quality.json")
    assert x["sessions"]==252
    assert x["strong_live_claims_allowed"] is False
    assert x["performance_comparison_allowed"] is False
    assert x["risk_comparison_allowed"] is False
    assert x["execution_cost_observable"] is False
    assert x["modeled_execution_cost_diagnostic_available"] is True
    assert x["independently_qualified_frozen8_sessions"]==0

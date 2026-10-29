"""Static and fixture regression for read-only StockLens cross-stack AWS audit."""
from pathlib import Path
import subprocess
import pytest
from infra.aws import stocklens_live_evidence_audit as audit

def test_audit_script_compiles():
    subprocess.run(["python", "-m", "py_compile",
                    "infra/aws/stocklens_live_evidence_audit.py"], check=True)

def test_reject_mutating_aws_operation():
    with pytest.raises(RuntimeError, match="FORBIDDEN_AWS_ACTION"):
        audit.cli("events", "enable-rule", "--name", "stocklens-st-signal")

def test_missing_s3_is_distinct_from_permission_denied(monkeypatch):
    def fake(kind, op, *args):
        raise RuntimeError("An error occurred (404) when calling the HeadObject operation: Not Found")
    monkeypatch.setattr(audit, "cli", fake)
    assert audit.head("a", "signals/2026-10-28.json") == {"status": "MISSING"}
    def denied(kind, op, *args):
        raise RuntimeError("An error occurred (403) when calling the HeadObject operation: Forbidden")
    monkeypatch.setattr(audit, "cli", denied)
    assert audit.head("a", "signals/2026-10-28.json")["status"] == "READ_ERROR"

def test_all_four_env_names_distinct():
    assert len(set(audit.NEW + [audit.OLD])) == 4
    assert audit.ACCOUNT == "634740393398"
    assert audit.REGION == "eu-central-1"

def test_no_orders_backfill_or_mutating_shell_calls():
    text=Path("infra/aws/stocklens_live_evidence_audit.py").read_text()
    assert '"aws_mutations": False' in text
    assert '"lambda_invocations": False' in text
    assert '"history_backfilled": False' in text
    assert '("dynamodb", "get-item")' in text
    assert '("logs", "filter-log-events")' in text
    for forbidden in ('"put-object"', '"update-stack"', '"enable-rule"',
                      '"invoke"', '"put-item"', '"send-order"'):
        assert forbidden not in text

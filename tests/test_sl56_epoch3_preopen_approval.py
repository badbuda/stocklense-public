"""Separate explicit consent shell requires approval, no broker or old-book mutation."""
import sys
from types import SimpleNamespace
import pytest
from infra.aws import sl56_epoch3_preopen_approval as m


def test_approval_without_exact_explicit_flag_is_rejected_before_boto3(monkeypatch):
    class BrokenBoto3:
        def __getattr__(self, value):
            pytest.fail("no AWS without explicit operator approval")
    monkeypatch.setitem(sys.modules,"boto3",BrokenBoto3())
    with pytest.raises(RuntimeError,match="EXPLICIT_OPERATOR_INCEPTION_APPROVAL_REQUIRED"):
        m.main(["approve"])
    with pytest.raises(RuntimeError,match="READ_ONLY_INSPECT_CANNOT_APPROVE"):
        m.main(["inspect","--approve-preopen-cash-100000"])


def test_readonly_inspect_has_no_simulated_capital_mutation(monkeypatch):
    calls=[]
    session=SimpleNamespace(client=lambda name:{"name":name})
    monkeypatch.setitem(sys.modules,"boto3",SimpleNamespace(
        Session=lambda **kw:session))
    monkeypatch.setattr(m.check,"preflight",lambda c:calls.append("preflight") or {
        "status":"ST_EPOCH3_READONLY_PREPARE_CHECK_PASS_NOT_DEPLOYMENT"})
    assert m.main(["inspect"])==0
    assert calls==["preflight"]


def test_preopen_tool_never_creates_genesis_or_changes_old_book(monkeypatch):
    from pathlib import Path
    source=Path("infra/aws/sl56_epoch3_preopen_approval.py").read_text()
    assert "approve_inception(" in source
    assert "create_genesis(" not in source
    assert "record_missing_history(" not in source
    assert "broker_orders" in source
    assert "historical_book_or_alarms_changed" in source
    for forbidden in ("delete_object(", "set_alarm_state(", "enable_rule(",
                      "disable_rule(", "invoke(", "update_function_code(",
                      "place_order(", "submit_order(", "execute_change_set("):
        assert forbidden not in source

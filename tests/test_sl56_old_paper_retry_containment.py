"""SL-56 old Paper containment only blocks repeated old gap retries, never alarms."""
from types import SimpleNamespace
from datetime import datetime, timezone
import pytest

from infra.aws import sl56_old_paper_retry_containment as m


def clients(*, code_sha=None, error_text=None, rule_state="ENABLED", target_ok=True):
    events = []
    rule="stocklens-st-paper-schedule"
    fn="stocklens-st-paper-candidate"
    arn="arn:aws:lambda:eu-central-1:634740393398:function:"+fn
    class EventBridge:
        def describe_rule(self,*,Name):
            assert Name==rule
            return {"State":rule_state,"ScheduleExpression":m.PAPER_CRON}
        def list_targets_by_rule(self,*,Rule):
            assert Rule==rule
            return {"Targets":[{"Arn":arn if target_ok else "wrong"}]}
        def disable_rule(self,*,Name):
            assert Name==rule
            events.append("ST_OLD_PAPER_RULE_DISABLED")
    c={
        "cloudformation":object(),
        "events":EventBridge(),
        "lambda":SimpleNamespace(get_function_configuration=lambda FunctionName:{
            "CodeSha256":code_sha or m.PAPER_LAMBDA_CODE_SHA_B64,
            "State":"Active","LastUpdateStatus":"Successful","FunctionArn":arn}),
        "logs":SimpleNamespace(filter_log_events=lambda **kw:{
            "events":[{"message":error_text or (
                "[ERROR] PaperIntegrityError: INTRADAY_FETCH_FAILED:QQQ:"+
                m.ERROR_CODE)}]}),
    }
    return c,events


def patch_readiness(monkeypatch):
    monkeypatch.setattr(m.check,"preflight",lambda c:{
        "old_book_gaps_still_absent":["2026-11-05","2026-11-06",
                                     "2026-11-09","2026-11-10","2026-11-11"]})
    monkeypatch.setattr(m.check,"stack_outputs",lambda cf,name:{
        "CandidatePaperFunctionName":"stocklens-st-paper-candidate",
        "CandidatePaperOnlyRuleName":"stocklens-st-paper-schedule",
    })


def test_exact_incident_only_and_alarm_not_suppressed(monkeypatch):
    patch_readiness(monkeypatch)
    c,events=clients()
    result=m.readiness(c)
    assert result["status"]=="ST_OLD_PAPER_RETRY_CONTAINMENT_PREFLIGHT_PASS"
    assert result["old_alarm_history_preserved"] is True
    assert result["new_epoch_running"] is False
    assert result["paper_trading_operational"] is False
    assert result["broker_orders"] is False
    assert events==[]


@pytest.mark.parametrize("change",[
    {"code_sha":"changed"},
    {"rule_state":"DISABLED"},
    {"target_ok":False},
    {"error_text":"unrelated-runtime-failure"},
])
def test_guard_rejects_unknown_runtime_state(monkeypatch,change):
    patch_readiness(monkeypatch)
    c,events=clients(**change)
    with pytest.raises(RuntimeError):
        m.readiness(c)
    assert events==[]


def test_source_does_not_mutate_monitoring_alarms_s3_lambda_or_production():
    from pathlib import Path
    source=Path("infra/aws/sl56_old_paper_retry_containment.py").read_text()
    assert source.count("disable_rule(")==1
    assert "ST_OLD_PAPER_SCHEDULE_PAUSED_GAP_STILL_OPEN" in source
    for forbidden in ("put_object(", "delete_object(", "set_alarm_state(",
                      "disable_alarm_actions(", "update_function_code(",
                      "update_function_configuration(", "execute_change_set(",
                      "enable_rule(", "place_order("):
        assert forbidden not in source
    assert "EXPLICIT_APPROVAL_REQUIRED_TO_PAUSE_ST_PAPER_RULE" in source

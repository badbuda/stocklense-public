"""Offline tests for the staged signal-only auto schedule.

The daily signal is intentionally independent from prospective Paper bootstrap.
No live AWS, Yahoo, broker or Clock injection at import.
"""
from datetime import datetime, timezone
from pathlib import Path
import json

import pytest

import infra.aws.independent_pipeline as pipeline


def test_after_nyse_close_scheduled_signal_calls_only_frozen_signal(monkeypatch):
    calls = []
    def frozen(**kwargs):
        calls.append(kwargs)
        return {"status": "STAGED_SIGNAL_ARCHIVED",
                "session": kwargs["expected_session"], "broker_actions": False}
    monkeypatch.setattr(pipeline, "run", frozen)
    fake_s3 = object()

    # 00:10 UTC Tuesday == Monday after 20:00 New York on Oct 12 (EDT).
    at = datetime(2026, 10, 13, 0, 10, tzinfo=timezone.utc)
    result = pipeline.run_scheduled_signal(now=at, s3=fake_s3, bucket="staging-only")
    assert result["session"] == "2026-10-12"
    assert result["broker_actions"] is False
    assert len(calls) == 1
    assert calls[0] == {
        "expected_session": "2026-10-12",
        "now": at,
        "s3": fake_s3,
        "bucket": "staging-only",
    }


def test_dst_change_still_after_18_new_york_and_calls_only_signal(monkeypatch):
    calls = []
    monkeypatch.setattr(pipeline, "run", lambda **kw: calls.append(kw) or
                        {"status": "STAGED_SIGNAL_ARCHIVED", "broker_actions": False})
    # First Monday after NY falls back to EST: Monday 19:10 NY.
    at = datetime(2026, 11, 3, 0, 10, tzinfo=timezone.utc)
    pipeline.run_scheduled_signal(now=at, s3=None, bucket="candidate")
    assert [call["expected_session"] for call in calls] == ["2026-11-02"]


def test_nyse_holiday_skips_without_any_ingest_write(monkeypatch):
    monkeypatch.setattr(pipeline, "run", lambda **kw: pytest.fail("NO_MARKET_WRITES_ON_HOLIDAY"))
    # Sat 00:10 UTC is Friday 19:10 NY. Christmas Dec 25 2026 is closed.
    result = pipeline.run_scheduled_signal(
        now=datetime(2026, 12, 26, 0, 10, tzinfo=timezone.utc),
        s3=None, bucket="candidate",
    )
    assert result == {
        "status": "SKIPPED_XNYS_NONTRADING_DAY",
        "broker_actions": False,
        "market_data_written": False,
    }


def test_before_market_completion_fails_closed(monkeypatch):
    monkeypatch.setattr(pipeline, "run", lambda **kw: pytest.fail("NO_BEFORE_CLOSE_WRITE"))
    with pytest.raises(RuntimeError, match="MARKET_DAY_NOT_YET_COMPLETE"):
        pipeline.run_scheduled_signal(
            now=datetime(2026, 10, 12, 20, 0, tzinfo=timezone.utc),
            s3=None, bucket="candidate",
        )


def test_cloudformation_signal_schedule_is_isolated_disabled_and_cost_bounded():
    import yaml

    class Loader(yaml.SafeLoader):
        pass
    Loader.add_multi_constructor(
        "!", lambda loader, suffix, node: suffix + ":" + str(node.value)
    )
    path = Path("infra/aws/independent-staging.yaml")
    doc = yaml.load(path.read_text(), Loader=Loader)
    r = doc["Resources"]
    signal = r["CandidateSignalOnlySchedule"]
    assert signal["Type"] == "AWS::Events::Rule"
    prop = signal["Properties"]
    assert prop["ScheduleExpression"] == "cron(30 2 ? * TUE-SAT *)"
    assert prop["State"] == "DISABLED"
    assert len(prop["Targets"]) == 1
    target = prop["Targets"][0]
    assert target["Arn"] == "GetAtt:CandidateLambda.Arn"
    assert json.loads(target["Input"]) == {"mode": "STAGING_SIGNAL_SCHEDULED"}
    invoke = r["CandidateSignalOnlySchedulePermission"]["Properties"]
    assert invoke["FunctionName"] == "Ref:CandidateLambda"
    assert invoke["SourceArn"] == "GetAtt:CandidateSignalOnlySchedule.Arn"
    assert r["CandidateOrchestratorSchedule"]["Properties"]["State"] == "DISABLED"
    assert doc["Outputs"]["CandidateSignalOnlyRuleName"]["Value"] == "Ref:CandidateSignalOnlySchedule"


def test_smoke_requires_new_signal_only_rule_disabled():
    shell = Path("infra/aws/smoke_independent_staging.sh").read_text()
    assert "CandidateSignalOnlyRuleName" in shell
    assert "SIGNAL_ONLY_NOT_SAFE_BY_DEFAULT" in shell

def test_signal_only_operator_opt_in_script_is_guarded_and_never_enables_paper():
    import subprocess
    script = Path("infra/aws/enable_staging_signal_only.sh")
    subprocess.run(["bash", "-n", str(script)], check=True)
    text = script.read_text()
    assert "StockLens-Whole-Account-20USD" in text
    assert "CandidateSignalOnlyRuleName" in text
    assert "CandidateOrchestratorRuleName" in text
    assert "PAPER_ORCHESTRATOR_NOT_DISABLED" in text
    assert "STAGING_SNS_EMAIL_UNCONFIRMED" in text
    assert "RECEIVED_STAGING_ALARM_EMAIL" in text
    assert text.count("aws events enable-rule") == 1
    assert "aws events disable-rule" not in text
    assert "aws cloudformation delete-stack" not in text
    assert "aws lambda update-function" not in text


def test_signal_watchdog_activation_deadline_and_dst():
    from infra.aws.independent_signal_monitor import due_signal_sessions
    def U(y,m,d,h,mi=0): return datetime(y,m,d,h,mi,tzinfo=timezone.utc)
    assert due_signal_sessions(U(2026,10,14,3,29), U(2026,10,13,12)) == []
    assert due_signal_sessions(U(2026,10,14,3,30), U(2026,10,13,12)) == [
        ("2026-10-13", U(2026,10,14,3,30))
    ]
    assert ("2026-11-02", U(2026,11,3,3,30)) in due_signal_sessions(
        U(2026,11,3,4), U(2026,11,2,12)
    )


def test_signal_watchdog_ignores_exchange_holidays_and_weekends():
    from infra.aws.independent_signal_monitor import due_signal_sessions
    def U(y,m,d,h): return datetime(y,m,d,h,tzinfo=timezone.utc)
    due = due_signal_sessions(U(2026,12,29,3), U(2026,12,24,12))
    days = [day for day, _ in due]
    assert "2026-12-24" in days and "2026-12-28" in days
    assert "2026-12-25" not in days and "2026-12-26" not in days


def test_signal_watchdog_missing_and_late_s3_receipts_alarm_without_paper():
    from infra.aws.independent_session_watchdog import inspect
    def U(y,m,d,h,mi=0): return datetime(y,m,d,h,mi,tzinfo=timezone.utc)
    common = dict(now=U(2026,10,15,5), rule_state="DISABLED",
                  expected_rule_state="DISABLED", monitoring_start=None,
                  read_record=lambda s: None, signal_rule_state="ENABLED",
                  signal_activation_at=U(2026,10,13,12))
    missing = inspect(**common, read_signal_saved_at=lambda day: None)
    assert missing["missing_scheduled_signals"] == ["2026-10-13", "2026-10-14"]
    assert missing["metrics"]["MissingOrLateScheduledSignals"] == 2
    assert missing["status"] == "FAIL_CLOSED"
    actual_times = {"2026-10-13": U(2026,10,14,3,31),
                    "2026-10-14": U(2026,10,15,0,20)}
    late = inspect(**common, read_signal_saved_at=actual_times.get)
    assert late["late_scheduled_signals"] == ["2026-10-13"]
    assert late["metrics"]["MissingOrLateScheduledSignals"] == 1
    assert late["status"] == "FAIL_CLOSED"
    on_time = inspect(**common, read_signal_saved_at=lambda d: U(
        2026,10,14,2,40) if d=="2026-10-13" else U(2026,10,15,2,40))
    assert on_time["metrics"]["MissingOrLateScheduledSignals"] == 0
    assert on_time["status"] == "PASS"


def test_signal_watchdog_detects_unexpected_disable_and_missing_activation():
    from infra.aws.independent_session_watchdog import inspect
    at = datetime(2026,10,14,tzinfo=timezone.utc)
    common = dict(now=at, rule_state="DISABLED",
                  expected_rule_state="DISABLED", monitoring_start=None,
                  read_record=lambda s: None)
    no_anchor = inspect(**common, signal_rule_state="ENABLED")
    assert "CONFIGURATION:SIGNAL_RULE_ENABLED_WITHOUT_ACTIVATION_ANCHOR" in no_anchor["failures"]
    disabled = inspect(**common, signal_rule_state="DISABLED",
                       signal_activation_at=datetime(2026,10,13,tzinfo=timezone.utc))
    assert "CONFIGURATION:SIGNAL_RULE_DISABLED_AFTER_ACTIVATION" in disabled["failures"]


def test_signal_watchdog_cf_scoping_and_operator_immutable_activation():
    import yaml
    class L(yaml.SafeLoader): pass
    L.add_multi_constructor("!", lambda ld, suffix, node: suffix + ":" + str(node.value))
    r = yaml.load(Path("infra/aws/independent-staging.yaml").read_text(), Loader=L)["Resources"]
    assert r["MissingOrLateScheduledSignalsAlarm"]["Properties"]["MetricName"] == "MissingOrLateScheduledSignals"
    env = r["CandidateSessionWatchdogLambda"]["Properties"]["Environment"]["Variables"]
    assert env["SIGNAL_ONLY_RULE"] == "Ref:CandidateSignalOnlySchedule"
    grants = r["CandidateSessionWatchdogRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    read_paths = []
    describe_rule_arns = []
    for grant in grants:
        actions = grant["Action"] if isinstance(grant["Action"], list) else [grant["Action"]]
        paths = grant["Resource"] if isinstance(grant["Resource"], list) else [grant["Resource"]]
        if "s3:GetObject" in actions: read_paths.extend(paths)
        if "events:DescribeRule" in actions: describe_rule_arns.extend(paths)
    assert any("monitoring/signal-only-activation.json" in p for p in read_paths)
    assert "GetAtt:CandidateSignalOnlySchedule.Arn" in describe_rule_arns
    operator = Path("infra/aws/enable_staging_signal_only.sh").read_text()
    import subprocess
    subprocess.run(["bash","-n","infra/aws/enable_staging_signal_only.sh"],check=True)
    assert "SIGNAL_ACTIVATION_ALREADY_ANCHORED_BUT_RULE_DISABLED" in operator
    assert "--if-none-match '*'" in operator
    assert operator.count("aws events enable-rule") == 1


def test_new_signal_monitor_module_is_in_lambda_deployment_artifact():
    """Packaging is explicit: passing local imports is not AWS ZIP import parity."""
    deploy = Path("infra/aws/deploy_independent_staging.sh").read_text()
    assert '"infra/aws/independent_signal_monitor.py",' in deploy
    assert '"infra/aws/independent_session_watchdog.py",' in deploy

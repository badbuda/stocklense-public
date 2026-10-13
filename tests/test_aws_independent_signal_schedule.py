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
    assert prop["ScheduleExpression"] == "cron(10 0 ? * TUE-SAT *)"
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

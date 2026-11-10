"""Integration regression: stale Monday is retried without an AWS write or false alert.

These are offline: no Yahoo, AWS or broker connections.
"""
from datetime import datetime, timezone
from pathlib import Path
import pytest

from infra.aws import independent_pipeline as pipeline
from infra.aws.independent_signal_monitor import due_signal_sessions
from infra.aws.independent_session_watchdog import inspect

UTC = timezone.utc
def dt(day, hour, minute=0):
    return datetime.fromisoformat(day + f"T{hour:02d}:{minute:02d}:00+00:00")

def stale(vendor="2026-11-06", audit="2026-11-06"):
    return ValueError(
        f"CANONICAL_INGEST_STALE_LAST_SESSION:expected=2026-11-09:"
        f"vendor_last={vendor}:audit_last={audit}"
    )

def test_monday_signal_deferred_no_side_effect(monkeypatch):
    requests = []
    def fake_run(**kw):
        requests.append(kw)
        raise stale()
    monkeypatch.setattr(pipeline, "run", fake_run)
    result = pipeline.run_scheduled_signal(
        now=dt("2026-11-10",5,30), s3=object(),bucket="fake-st")
    assert result["status"] == "DEFER_VENDOR_NOT_PUBLISHED"
    assert result["observed_vendor_session"] == "2026-11-06"
    assert result["expected_session"] == "2026-11-09"
    assert result["market_data_written"] is False
    assert result["broker_actions"] is False
    assert result["automatic_backfill"] is False
    assert len(requests) == 1

def test_monday_lag_beyond_last_deadline_is_a_hard_error(monkeypatch):
    monkeypatch.setattr(pipeline, "run", lambda **kw: (_ for _ in ()).throw(stale()))
    with pytest.raises(ValueError, match="CANONICAL_INGEST_STALE_LAST_SESSION"):
        pipeline.run_scheduled_signal(now=dt("2026-11-10",12,30),
                                      s3=object(), bucket="fake-st")

def test_unexpected_audit_disagreement_remains_alarmable(monkeypatch):
    monkeypatch.setattr(pipeline, "run", lambda **kw: (_ for _ in ()).throw(
        stale(audit="2026-11-05")))
    with pytest.raises(ValueError, match="STALE_LAST_SESSION"):
        pipeline.run_scheduled_signal(now=dt("2026-11-10",8,30),
                                      s3=object(), bucket="fake-st")

def test_noncanonical_exception_remains_alarmable(monkeypatch):
    monkeypatch.setattr(pipeline, "run", lambda **kw: (_ for _ in ()).throw(
        ValueError("CANONICAL_INGEST_BAD_PRICE")))
    with pytest.raises(ValueError, match="BAD_PRICE"):
        pipeline.run_scheduled_signal(now=dt("2026-11-10",8,30),
                                      s3=object(), bucket="fake-st")

def test_v2_monitor_only_changes_prospective_sessions():
    activated=dt("2026-10-28", 12)
    old=due_signal_sessions(dt("2026-11-10",12,20),activated,
                             v2_start_session="2026-11-09")
    oldmap=dict(old)
    assert oldmap["2026-11-06"] == dt("2026-11-07",3,30)
    assert "2026-11-09" not in oldmap
    after=due_signal_sessions(dt("2026-11-10",12,30),activated,
                               v2_start_session="2026-11-09")
    assert dict(after)["2026-11-09"] == dt("2026-11-10",12,30)

def test_watchdog_v2_defers_missing_until_final_deadline():
    opts=dict(rule_state="DISABLED",expected_rule_state="DISABLED",
              monitoring_start=None,read_record=lambda _:None,
              signal_rule_state="ENABLED",
              signal_activation_at=dt("2026-11-09",12),
              signal_v2_start_session="2026-11-09",
              read_signal_saved_at=lambda _:None)
    early=inspect(now=dt("2026-11-10",12,0), **opts)
    assert early["latest_due_signal_status"] == "NOT_DUE"
    assert early["metrics"]["MissingOrLateScheduledSignals"] == 0
    due=inspect(now=dt("2026-11-10",12,30), **opts)
    assert due["latest_due_signal_status"] == "MISSING"
    assert due["metrics"]["MissingOrLateScheduledSignals"] == 1

def test_missing_paper_integrity_not_silenced_by_signal_delay():
    report=inspect(now=dt("2026-11-10",12,30),
                   rule_state="DISABLED",expected_rule_state="DISABLED",
                   monitoring_start="2026-10-30",
                   read_record=lambda _:None,read_genesis=lambda:None,
                   signal_rule_state="ENABLED",
                   signal_activation_at=dt("2026-11-09",12),
                   signal_v2_start_session="2026-11-09",
                   read_signal_saved_at=lambda _:None)
    assert report["status"] == "FAIL_CLOSED"
    assert report["metrics"]["MissingOrLateScheduledSignals"] == 1
    assert "2026-10-30" in report["missed_sessions"]

def test_zip_includes_retry_module_and_st_template_requires_explicit_activation():
    deploy=Path("infra/aws/deploy_independent_staging.sh").read_text()
    assert '"stocklens/st_signal_retry_policy.py",' in deploy
    template=Path("infra/aws/independent-staging.yaml").read_text()
    assert "SignalV2StartSession:" in template
    assert "SIGNAL_V2_START_SESSION: !Ref SignalV2StartSession" in template
    assert "cron(30 5,8,11,12 ? * TUE-SAT *)" in template
    assert "cron(45 12 ? * TUE-SAT *)" in template


def test_retries_resolve_previous_new_york_day_after_midnight():
    f=pipeline.completed_session_for_scheduled_attempt
    for hour in (5,8,11):
        assert f(dt("2026-11-10",hour,30)) == "2026-11-09"
    # Before the DST change, New York is one hour further ahead.
    for hour in (5,8,11):
        assert f(dt("2026-10-13",hour,30)) == "2026-10-12"

def test_after_open_must_not_reinterpret_todays_partial_session():
    with pytest.raises(RuntimeError,match="MARKET_DAY_NOT_YET_COMPLETE"):
        pipeline.completed_session_for_scheduled_attempt(
            dt("2026-11-10",16,0)
        )

def test_nontrading_day_skips_rather_than_look_back_many_sessions():
    # Monday 2026-12-28 follows Friday Christmas holiday.
    assert pipeline.completed_session_for_scheduled_attempt(
        dt("2026-12-26",5,30)
    ) is None


def test_paper_next_new_york_morning_selects_prior_completed_session(monkeypatch):
    """12:45 UTC Tuesday is pre-open NY, never the incomplete Tuesday session."""
    from infra.aws import independent_paper as paper
    monkeypatch.setattr(paper, "_read_genesis", lambda *_: None)
    with pytest.raises(RuntimeError, match="AUTOMATED_PAPER_FORBIDDEN_WITHOUT_VERIFIED_GENESIS"):
        paper.run_scheduled_paper(
            now=dt("2026-11-10", 12, 45), s3=object(), bucket="fake-st"
        )

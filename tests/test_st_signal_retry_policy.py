"""No AWS access; prove Monday-after-weekend safety and stale-fail behavior."""
from datetime import datetime, timezone
from stocklens.st_signal_retry_policy import (
    classify, deadline_for, assert_safe_time_window,
    SIGNAL_RETRY_CRON, PAPER_AFTER_SIGNAL_CRON,
)

UTC = timezone.utc
def at(day, hour, minute=0):
    return datetime.fromisoformat(day + f"T{hour:02d}:{minute:02d}:00+00:00")

def judge(vendor, audit, now, session="2026-11-09", xnys=True):
    return classify(expected_session=session, vendor_last=vendor,
                    audit_last=audit, now_utc=now, is_xnys_session=xnys)

def test_monday_friday_bar_is_deferred_without_promoting_friday():
    value=judge("2026-11-06", "2026-11-06", at("2026-11-10", 5, 30))
    assert value.status == "DEFER_VENDOR_NOT_PUBLISHED"
    assert value.signal_may_publish is False
    assert value.should_raise_alarm is False
    assert value.expected_session == "2026-11-09"

def test_monday_late_vendor_appears_before_cutoff():
    value=judge("2026-11-09","2026-11-09",at("2026-11-10",11,30))
    assert value.status=="READY_FOR_FROZEN_VALIDATION"
    assert value.signal_may_publish and not value.should_raise_alarm

def test_monday_bar_missing_at_deadline_is_a_real_incident():
    value=judge("2026-11-06","2026-11-06",at("2026-11-10",12,50))
    assert value.status=="MISSING_VENDOR_BAR_AFTER_DEADLINE"
    assert value.should_raise_alarm
    assert not value.signal_may_publish

def test_audit_mismatch_is_not_deferred():
    value=judge("2026-11-09","2026-11-06",at("2026-11-10",5,30))
    assert value.status=="BLOCKED_SOURCE_AUDIT_DISAGREEMENT"
    assert value.should_raise_alarm

def test_no_future_bar_leak():
    try:
        judge("2026-11-10","2026-11-10",at("2026-11-10",5,30))
        assert False
    except ValueError as exc:
        assert "FUTURE_VENDOR_BAR" in str(exc)

def test_non_trading_session_rejected():
    try:
        judge("2026-11-06","2026-11-06",at("2026-11-10",5,30),
              session="2026-11-08",xnys=False)
        assert False
    except ValueError as exc:
        assert "NOT_XNYS_SESSION" in str(exc)

def test_no_early_current_day_signal():
    try:
        judge("2026-11-09","2026-11-09",at("2026-11-09",19))
        assert False
    except ValueError as exc:
        assert "CURRENT_SESSION_MAY_NOT_BE_COMPLETE" in str(exc)

def test_no_history_backfill_or_lookahead():
    try:
        judge("2026-11-06","2026-11-06",at("2026-11-20",11))
        assert False
    except ValueError as exc:
        assert "SIGNAL_SESSION_EXPIRED" in str(exc)

def test_friday_close_and_holiday_skip_deadline():
    assert deadline_for("2026-11-06").isoformat()=="2026-11-07T12:50:00+00:00"
    assert deadline_for("2026-11-09").isoformat()=="2026-11-10T12:50:00+00:00"

def test_all_retries_pre_open_and_paper_after_signal():
    assert assert_safe_time_window()
    assert SIGNAL_RETRY_CRON == "cron(30 5,8,11,12 ? * TUE-SAT *)"
    assert PAPER_AFTER_SIGNAL_CRON == "cron(0 13 ? * TUE-SAT *)"

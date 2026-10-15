"""Adversarial follow-up regression tests for Claude's PR #78 continuity patch.

Expected to FAIL against the uploaded patch. They specify safety properties
to satisfy before deploying the proposed change. No AWS/network/broker access.

Place alongside tests/test_aws_session_continuity.py from Claude's patch.
"""
from datetime import datetime, timezone
import pytest

from stocklens.paper import PaperIntegrityError

from infra.aws import session_continuity as sc
from infra.aws.independent_session_watchdog import inspect
from infra.aws.independent_paper import run_paper, run_paper_catchup
from test_aws_session_continuity import _bootstrap, seed, fetch, U


def test_paper_completion_time_must_use_actual_s3_write_time():
    """Lambda starts at 09:29 next day but S3 receipt lands 09:31."""
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00",
         U(2026, 10, 12, 23, 1))
    s3.clock = U(2026, 10, 13, 13, 31)  # after next XNYS open (09:30 EDT)
    result = run_paper(
        session="2026-10-12",
        now=U(2026, 10, 13, 13, 29),  # Lambda's START time
        s3=s3, bucket="b", market_fetch=fetch)
    # Must NOT classify as on-time based on processing start.
    assert result["continuity_status"] != sc.ON_TIME


def test_manual_bootstrap_must_not_bypass_halted_epoch():
    """A MISSED Monday must not permit resetting the same Paper book Tuesday."""
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00",
         U(2026, 10, 12, 23, 1))
    seed(s3, "2026-10-13", "2026-10-13T23:00:00+00:00",
         U(2026, 10, 13, 23, 1))
    s3.clock = U(2026, 10, 12, 23, 30)

    def unavailable(prior, day):
        # Policy change agreed in review v3: a transient TimeoutError is retried, not
        # MISSED. "Bars unavailable" is now expressed by the provider's absence code.
        raise PaperIntegrityError("MISSING_0931_BAR:TQQQ:" + day)

    first = run_paper_catchup(
        target_session="2026-10-12", now=U(2026, 10, 12, 23, 30),
        s3=s3, bucket="b", market_fetch=unavailable)
    assert first["status"] == "STAGED_PAPER_HALTED"
    s3.clock = U(2026, 10, 13, 23, 30)
    with pytest.raises((RuntimeError, ValueError), match="HALTED|REBOOTSTRAP|BOOK"):
        run_paper(session="2026-10-13",
                  now=U(2026, 10, 13, 23, 30),
                  s3=s3, bucket="b", bootstrap=True, market_fetch=fetch)


def test_missed_continuity_record_cannot_be_silently_replaced_by_success():
    """An immutable MISSED classification must prevent later Paper fill insertion."""
    s3 = _bootstrap()
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00",
         U(2026, 10, 12, 23, 1))
    s3.clock = U(2026, 10, 12, 23, 30)

    def unavailable(prior, day):
        # Policy change agreed in review v3: a transient TimeoutError is retried, not
        # MISSED. "Bars unavailable" is now expressed by the provider's absence code.
        raise PaperIntegrityError("MISSING_0931_BAR:TQQQ:" + day)

    first = run_paper_catchup(
        target_session="2026-10-12", now=U(2026, 10, 12, 23, 30),
        s3=s3, bucket="b", market_fetch=unavailable)
    assert first["status"] == "STAGED_PAPER_HALTED"
    with pytest.raises((RuntimeError, ValueError), match="HALTED|MISSED|CONFLICT"):
        run_paper(session="2026-10-12",
                  now=U(2026, 10, 12, 23, 30),
                  s3=s3, bucket="b", market_fetch=fetch)


def test_idempotent_catchup_returns_existing_receipt_sha_not_null():
    """Second invocation should prove the existing Paper receipt, not return null."""
    s3 = _bootstrap()
    again = run_paper_catchup(target_session="2026-10-09",
                              now=U(2026, 10, 9, 23, 31),
                              s3=s3, bucket="b", market_fetch=fetch)
    assert again["status"] == "STAGED_PAPER_CATCHUP_COMPLETED"
    assert isinstance(again["paper_sha256"], str) and len(again["paper_sha256"]) == 64


def test_watchdog_rejects_present_but_invalid_continuity_record():
    """Mere existence of an arbitrary JSON object is NOT a valid healthy receipt."""
    result = inspect(
        now=U(2026, 10, 15, 18),
        rule_state="ENABLED",
        expected_rule_state="ENABLED",
        monitoring_start="2026-10-12",
        read_record=lambda session: {"status": "FORGED", "book_halted": False})
    assert result["status"] == "FAIL_CLOSED"
    assert result["metrics"]["MissedSessions"] > 0 or result["metrics"].get("InvalidReceipts", 0) > 0


def test_watchdog_missing_monitoring_start_must_set_alarm_metric():
    """FAIL_CLOSED in a log isn't enough when every alarmed metric is zero."""
    result = inspect(now=U(2026, 10, 15, 18),
                     rule_state="ENABLED", expected_rule_state="ENABLED",
                     monitoring_start=None, read_record=lambda session: None)
    assert result["status"] == "FAIL_CLOSED"
    assert any(
        result["metrics"].get(key, 0) > 0
        for key in ("MissedSessions", "SchedulerStateMismatch", "BookHalted", "ConfigurationError")
    )


def test_pure_classification_does_not_accept_pre_close_paper_accounting():
    """Defensive contract: completion must be after XNYS close, not just before next open."""
    status = sc.classify(
        session="2026-10-12", signal_archived_at=U(2026, 10, 9, 23),
        processed_at=U(2026, 10, 12, 14),
        accounting_completed=True)
    assert status != sc.ON_TIME

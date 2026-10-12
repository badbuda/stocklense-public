"""Red-team acceptance tests for PR #78 continuity v3, 2026-10-12.

Place in tests/test_pr78_v3_redteam.py on the PR branch AFTER applying v3.
All tests are deliberately written as safety requirements expected to FAIL on v3.
They must pass before enabling independent session monitoring or staging deployment.
They perform NO network calls, broker actions, or AWS writes.
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import json

import pytest

from infra.aws import session_continuity as sc
from infra.aws.independent_session_watchdog import inspect
from infra.aws.independent_paper import run_paper, GENESIS_KEY
from test_aws_session_continuity import U, S3, _bootstrap, seed, fetch


def test_sns_alarm_topic_must_not_use_aws_managed_sns_kms_key():
    """AWS says CloudWatch alarms cannot use SNS encrypted with alias/aws/sns."""
    template = Path("infra/aws/independent-staging.yaml").read_text(encoding="utf-8")
    assert "KmsMasterKeyId: alias/aws/sns" not in template, (
        "CloudWatch alarm actions cannot use the AWS-managed aws/sns KMS key. "
        "Use a customer-managed KMS key granting cloudwatch.amazonaws.com "
        "kms:GenerateDataKey* and kms:Decrypt, or redesign the topic."
    )


def test_watchdog_must_verify_real_book_genesis_not_just_first_continuity_record():
    """A forged local genesis cannot satisfy a real book's anchor requirement."""
    session = "2026-10-13"  # Suppose durable genesis was actually 2026-10-09
    prior = sc.previous_session(session)
    signal_at = sc.session_close_utc(prior) + timedelta(hours=1)
    receipt_at = sc.session_close_utc(session) + timedelta(hours=1)
    fake_sha = "a" * 64
    forged = sc.build_record(
        session=session, status=sc.ON_TIME,
        previous_record=None, previous_record_sha256=None,
        processed_at=receipt_at, signal_archived_at=signal_at,
        book=sc.BOOK, evidence={"paper_sha256": fake_sha})
    result = inspect(
        now=U(2026, 10, 14, 18),
        rule_state="ENABLED", expected_rule_state="ENABLED",
        monitoring_start=session,
        read_record=lambda day: forged if day == session else None,
        read_receipt_sha=lambda day: fake_sha if day == session else None,
        read_last_modified=lambda key: (
            receipt_at if key == f"paper/sessions/{session}.json"
            else signal_at if key == f"signals/{prior}.json"
            else None),
    )
    # No genesis object or hash was supplied or verified, so PASS is unwarranted.
    assert result["status"] == "FAIL_CLOSED", result


def test_manual_staging_paper_is_monitored_even_when_orchestrator_is_disabled():
    """Disabled trading orchestration must not disable Paper receipt completeness."""
    result = inspect(
        now=U(2026, 10, 15, 18),
        rule_state="DISABLED",
        expected_rule_state="DISABLED",
        monitoring_start="2026-10-09",  # book monitoring explicitly started
        read_record=lambda session: None,
        read_receipt_sha=lambda session: None,
    )
    assert result["status"] == "FAIL_CLOSED"
    assert result["metrics"]["MissedSessions"] >= 1


def test_tampered_previous_record_cannot_trigger_new_paper_receipt_write():
    """Preflight must recompute predecessor counters / verify continuity first."""
    s3 = _bootstrap()
    day = "2026-10-09"
    key = f"paper/continuity/{day}.json"
    forged = json.loads(s3.data[key])
    forged["qualified_streak_in_epoch"] = 252
    forged["epoch"] = 999
    s3.data[key] = sc.canonical(forged)
    seed(s3, "2026-10-12", "2026-10-12T23:00:00+00:00",
         U(2026, 10, 12, 23, 1))
    s3.clock = U(2026, 10, 12, 23, 30)
    keys_before = set(s3.data)

    with pytest.raises((RuntimeError, ValueError), match="(PREVIOUS|CHAIN|UNVERIFIED|INTEGRITY)"):
        run_paper(session="2026-10-12",
                  now=U(2026, 10, 12, 23, 30),
                  s3=s3, bucket="b", market_fetch=fetch)
    assert set(s3.data) == keys_before, "No new market/Paper/continuity artifacts allowed"


def test_failed_bootstrap_validation_cannot_leave_orphan_genesis():
    """Validate candidate session and complete accounting before persisting genesis."""
    s3 = S3()
    seed(s3, "2026-10-08", "2026-10-08T23:00:00+00:00",
         U(2026, 10, 8, 23, 1))
    seed(s3, "2026-10-09", "2026-10-09T23:00:00+00:00",
         U(2026, 10, 9, 23, 1))
    bad = json.loads(s3.data["signals/2026-10-09.json"])
    bad["latest"]["level"] = 99
    s3.data["signals/2026-10-09.json"] = json.dumps(bad).encode()
    s3.clock = U(2026, 10, 9, 23, 30)
    with pytest.raises(ValueError, match="INVALID_FROZEN_LEVEL"):
        run_paper(session="2026-10-09",
                  now=U(2026, 10, 9, 23, 30),
                  s3=s3, bucket="b", bootstrap=True,
                  market_fetch=fetch)
    assert GENESIS_KEY not in s3.data, (
        "Failed bootstrap must not strand immutable genesis without a verified receipt"
    )

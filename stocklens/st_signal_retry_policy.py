"""Prospective ST signal vendor-lag policy, independent of the frozen strategy.

V2 contract only: a missing vendor bar is retryable *until* a fixed pre-open
deadline, never silently replaced by Friday's candle. This module is pure;
it does not change EventBridge, CloudWatch, S3 or any Lambda by itself.
Private ST adapter and epoch-scoped watchdog must integrate it together.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

POLICY_VERSION = "ST_SIGNAL_VENDOR_LAG_V2"
# UTC next-calendar-day schedule, following the previous completed XNYS day.
# Includes a final one-hour qualification window before the alert deadline.
SIGNAL_RETRY_CRON = "cron(30 5,8,11,12 ? * TUE-SAT *)"
PAPER_AFTER_SIGNAL_CRON = "cron(45 12 ? * TUE-SAT *)"
RECEIPT_DEADLINE_UTC = time(12, 30)
MAX_WAIT_DAYS = 5

@dataclass(frozen=True)
class Verdict:
    status: str
    expected_session: str
    observed_vendor_session: str | None
    observed_audit_session: str | None
    deadline_utc: str
    signal_may_publish: bool
    should_raise_alarm: bool
    explanation: str

def deadline_for(session: str) -> datetime:
    day = date.fromisoformat(session)
    if day.isoformat() != session:
        raise ValueError("INVALID_NONCANONICAL_SESSION")
    return datetime.combine(day + timedelta(days=1), RECEIPT_DEADLINE_UTC, timezone.utc)

def classify(
    *,
    expected_session: str,
    vendor_last: str | None,
    audit_last: str | None,
    now_utc: datetime,
    is_xnys_session: bool,
) -> Verdict:
    """Evaluate source completeness without market writes, fills, or lookahead.

    Adapter must still perform source fingerprint, calendar, historical
    completeness and price checks before archiving. 'READY_FOR_VALIDATION'
    is NOT permission to publish or trade.
    """
    if now_utc.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    now = now_utc.astimezone(timezone.utc)
    deadline = deadline_for(expected_session)
    session_day = date.fromisoformat(expected_session)
    if not is_xnys_session:
        raise ValueError("NOT_XNYS_SESSION")
    if now < datetime.combine(session_day + timedelta(days=1), time(0), timezone.utc):
        raise ValueError("CURRENT_SESSION_MAY_NOT_BE_COMPLETE")
    if (now.date() - session_day).days > MAX_WAIT_DAYS:
        raise ValueError("SIGNAL_SESSION_EXPIRED")
    for key, value in (("vendor", vendor_last), ("audit", audit_last)):
        if value is not None:
            parsed = date.fromisoformat(value)
            if parsed.isoformat() != value:
                raise ValueError("NONCANONICAL_" + key.upper() + "_DATE")
            if parsed > session_day:
                raise ValueError("FUTURE_" + key.upper() + "_BAR")

    def result(state: str, publish: bool, alarm: bool, detail: str) -> Verdict:
        return Verdict(
            status=state, expected_session=expected_session,
            observed_vendor_session=vendor_last,
            observed_audit_session=audit_last,
            deadline_utc=deadline.isoformat(),
            signal_may_publish=publish, should_raise_alarm=alarm,
            explanation=detail,
        )
    if vendor_last != audit_last:
        return result("BLOCKED_SOURCE_AUDIT_DISAGREEMENT", False, True,
                      "Vendor and canonical source audit disagree; no fallback.")
    if vendor_last == expected_session:
        return result("READY_FOR_FROZEN_VALIDATION", True, False,
                      "Date matches only; perform ALL frozen source gates.")
    if now < deadline:
        return result("DEFER_VENDOR_NOT_PUBLISHED", False, False,
                      "Wait for a fresh scheduled invocation; no S3 writes.")
    return result("MISSING_VENDOR_BAR_AFTER_DEADLINE", False, True,
                  "Pre-open deadline expired; fail closed and alert.")

def assert_safe_time_window():
    """Avoid edits that schedule the next day's session after NYSE can open.

    13:30 UTC is the earliest regular 09:30 New York open during DST.
    The final scheduled attempt + monitoring deadline must be earlier.
    """
    last_try = time(12, 30)
    if not (last_try <= RECEIPT_DEADLINE_UTC < time(13, 30)):
        raise RuntimeError("RETRY_POLICY_CROSSES_NEXT_US_OPEN")
    if "TUE-SAT" not in SIGNAL_RETRY_CRON:
        raise RuntimeError("SCHEDULE_WRONG_WEEKDAY_WINDOW")
    if "12" not in PAPER_AFTER_SIGNAL_CRON:
        raise RuntimeError("PAPER_NOT_MOVED_AFTER_RETRY")
    return True

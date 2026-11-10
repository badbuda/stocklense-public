"""Calendar-aware scheduled-signal coverage (no AWS calls or side effects)."""
from __future__ import annotations
from datetime import datetime, date, time, timedelta, timezone

SCHEDULE_UTC = time(2, 30)
GRACE = timedelta(hours=1)
MAX_SESSIONS = 400


def due_signal_sessions(now: datetime, activation_at: datetime,
                        v2_start_session: str | None = None) -> list[tuple[str, datetime]]:
    """Return (XNYS session, UTC receipt deadline) only for runs after activation.

    The scheduled UTC invocation at 02:30 is on the next calendar day after
    the NYSE session, including Fridays. This holds across US DST changes.
    """
    if now.tzinfo is None or activation_at.tzinfo is None:
        raise ValueError("SIGNAL_WATCH_CLOCK_MUST_BE_AWARE")
    now = now.astimezone(timezone.utc)
    activation_at = activation_at.astimezone(timezone.utc)
    if activation_at > now:
        raise ValueError("ACTIVATION_AFTER_OBSERVATION_TIME")
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS")
    first_date = max(date(2008, 1, 1), (activation_at - timedelta(days=2)).date())
    last_date = (now - timedelta(days=1)).date()
    if last_date < first_date:
        return []
    first = cal.date_to_session(first_date.isoformat(), direction="next")
    last = cal.date_to_session(last_date.isoformat(), direction="previous")
    if first > last:
        return []
    sessions = list(cal.sessions_in_range(first, last))
    if len(sessions) > MAX_SESSIONS + 3:
        raise RuntimeError("SIGNAL_WATCH_CHECKPOINT_REQUIRED")
    # Preserve the immutable historical 03:30 deadline for old sessions.
    # Only a separately authorized, prospective V2 session may use the
    # pre-open 12:30 deadline; never relabel past late receipts as on time.
    v2_date = None
    if v2_start_session:
        v2_date = date.fromisoformat(v2_start_session)
        if v2_date.isoformat() != v2_start_session or not cal.is_session(v2_start_session):
            raise ValueError("SIGNAL_V2_ACTIVATION_NOT_XNYS_SESSION")
    due = []
    for sess in sessions:
        day = sess.date()
        scheduled = datetime.combine(day + timedelta(days=1), SCHEDULE_UTC, tzinfo=timezone.utc)
        if v2_date is not None and day >= v2_date:
            from stocklens.st_signal_retry_policy import deadline_for
            deadline = deadline_for(day.isoformat())
        else:
            deadline = scheduled + GRACE
        if scheduled > activation_at and deadline <= now:
            due.append((day.isoformat(), deadline))
    return due

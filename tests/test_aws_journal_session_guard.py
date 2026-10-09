"""Historical XNYS-aware session audit; no AWS requests are made here."""
from datetime import datetime, timezone
import pytest
from aws_journal_session_guard import evaluate


@pytest.mark.parametrize("utc_at,session,expected", [
    ("2026-10-10T09:40:00+00:00", "2026-10-09", True),   # regular Friday
    ("2026-04-04T09:40:00+00:00", "2026-04-03", False),  # Good Friday
    ("2026-06-20T09:40:00+00:00", "2026-06-19", False),  # Juneteenth
    ("2026-07-04T09:40:00+00:00", "2026-07-03", False),  # observed July 4
    ("2026-11-28T09:40:00+00:00", "2026-11-27", True),   # Black Friday half-day
    ("2026-12-26T09:40:00+00:00", "2026-12-25", False),  # Christmas
    ("2026-10-11T09:40:00+00:00", "2026-10-10", False),  # weekend
])
def test_xnys_archive_requirements(utc_at, session, expected):
    outcome=evaluate(datetime.fromisoformat(utc_at))
    assert outcome["session"] == session
    assert outcome["expected"] is expected
    assert outcome["status"] == ("ARCHIVE_EXPECTED" if expected else "NO_XNYS_SESSION_NO_ARCHIVE_EXPECTED")
    assert outcome["eventbridge_rule_enabled_verified"] is False


def test_naive_datetime_is_rejected():
    with pytest.raises(ValueError, match="TIME_MUST_BE_TIMEZONE_AWARE"):
        evaluate(datetime(2026,10,10,9,40))


def test_calendar_failure_is_not_silenced():
    class CalendarUnavailable:
        def is_session(self, day):
            raise RuntimeError("CALENDAR_NOT_AVAILABLE")
    with pytest.raises(RuntimeError, match="CALENDAR_NOT_AVAILABLE"):
        evaluate(datetime(2026,10,10,9,40,tzinfo=timezone.utc),CalendarUnavailable())

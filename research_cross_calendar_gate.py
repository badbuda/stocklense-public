"""SL9-030: cross-calendar causal *feasibility*, never first-seen certification.

The XNYS equities calendar is NOT the SEC EDGAR, Treasury/bond or Federal
Reserve publication calendar. US federal holidays are only a conservative
EDGAR-day proxy, not an independently authenticated SEC operational schedule.
No outcome, alpha, or live trading is produced by this module.
"""
from __future__ import annotations

import json
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import exchange_calendars as xcals
from pandas.tseries.holiday import USFederalHolidayCalendar

NY = ZoneInfo("America/New_York")
# SEC's published exceptions to the ordinary post-17:30 next-business-day rule.
# https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/determine-status-my-filing
SAME_DAY_LATE_FORMS = frozenset({
    "3", "3/A", "4", "4/A", "5", "5/A", "144", "144/A",
    "F-1MEF", "F-3MEF", "F-4MEF", "N-14MEF", "N-2MEF",
    "POS 462B", "S-11MEF", "S-1MEF", "S-3MEF", "S-4MEF", "S-BMEF",
})


def _parse_utc(s: str) -> datetime:
    if not isinstance(s, str) or not s or len(s) > 64:
        raise ValueError("MISSING_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("INVALID_TIMESTAMP") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return parsed.astimezone(timezone.utc)


def _federal_holidays(start: date, end: date) -> set[date]:
    return {d.date() for d in USFederalHolidayCalendar().holidays(start=start, end=end)}


def is_federal_business_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _federal_holidays(d, d)


def next_federal_business_day(d: date) -> date:
    candidate = d + timedelta(days=1)
    for _ in range(14):
        if is_federal_business_day(candidate):
            return candidate
        candidate += timedelta(days=1)
    raise ValueError("NO_FEDERAL_BUSINESS_DAY_WITHIN_14_DAYS")


def sec_dissemination_lower_bound(*, form: str,
                                  transmission_started_at_utc: str,
                                  accepted_at_utc: str) -> dict:
    """Earliest *possible* dissemination date, never an observed first-seen.

    SEC says most filings transmitted after 17:30 ET wait for next EDGAR
    business day; specified exception forms can be disseminated until 22:00.
    A transmission timestamp is required: acceptance time alone is NOT enough.
    """
    if not isinstance(form, str) or not form or len(form) > 32:
        raise ValueError("INVALID_FORM")
    started = _parse_utc(transmission_started_at_utc)
    accepted = _parse_utc(accepted_at_utc)
    if accepted < started:
        raise ValueError("ACCEPTED_BEFORE_TRANSMISSION")
    local = started.astimezone(NY)
    day = local.date()
    if not is_federal_business_day(day):
        raise ValueError("FEDERAL_HOLIDAY_OR_WEEKEND_REQUIRES_SEC_CALENDAR_EVIDENCE")
    if not time(6, 0) <= local.time() < time(22, 0):
        raise ValueError("OUTSIDE_EDGAR_OPERATING_WINDOW")
    late = local.time() > time(17, 30)
    accepted_local = accepted.astimezone(NY)
    # A post-close or later-day acceptance cannot justify same-day access,
    # even for an exception form whose transmission started before 22:00.
    same_day_accepted = (accepted_local.date() == day and
                         accepted_local.time() < time(22, 0))
    deferred = (late and form.upper() not in SAME_DAY_LATE_FORMS) or not same_day_accepted
    earliest = next_federal_business_day(day) if deferred else day
    while earliest < accepted_local.date() or not is_federal_business_day(earliest):
        earliest = next_federal_business_day(earliest)
    return {
        "kind": "SEC_EARLIEST_POSSIBLE_DISSEMINATION_DAY",
        "form": form.upper(),
        "transmission_started_et": local.isoformat(),
        "accepted_at_utc": accepted.isoformat(),
        "after_1730_et": late,
        "published_form_exception": form.upper() in SAME_DAY_LATE_FORMS,
        "earliest_possible_date": earliest.isoformat(),
        "calendar_source": "US_FEDERAL_HOLIDAY_PROXY_NOT_AUTHENTICATED_EDGAR_CALENDAR",
        "actual_public_first_seen_verified": False,
        "tradable_event_qualified": False,
        "broker_orders_authorized": False,
        "automatic_promotion": False,
    }


def next_equity_open_after(received_at_utc: str) -> str:
    """Strictly future regular XNYS open; not executable bid/ask proof."""
    received = _parse_utc(received_at_utc)
    cal = xcals.get_calendar("XNYS")
    start = (received.astimezone(NY).date() - timedelta(days=1)).isoformat()
    end = (received.astimezone(NY).date() + timedelta(days=20)).isoformat()
    for session in cal.sessions_in_range(start, end):
        opening = cal.session_open(session).to_pydatetime().astimezone(timezone.utc)
        if opening > received:
            return opening.isoformat()
    raise ValueError("NO_NEXT_XNYS_OPEN_WITHIN_20_DAYS")


def audit_year(year: int) -> dict:
    if type(year) is not int or not 2000 <= year <= 2050:
        raise ValueError("UNSUPPORTED_YEAR")
    cal = xcals.get_calendar("XNYS")
    start, end = date(year, 1, 1), date(year, 12, 31)
    sessions = {s.date() for s in cal.sessions_in_range(start.isoformat(), end.isoformat())}
    federal = _federal_holidays(start, end)
    collisions = sorted(sessions & federal)
    return {
        "kind": "XNYS_VS_US_FEDERAL_HOLIDAY_FEASIBILITY",
        "year": year,
        "xnys_sessions": len(sessions),
        "observed_federal_holidays": len(federal),
        "xnys_open_federal_holidays": [d.isoformat() for d in collisions],
        "collision_count": len(collisions),
        "sec_edgar_calendar_independently_verified": False,
        "fred_release_calendar_independently_verified": False,
        "independently_qualified_pit_rows": 0,
        "historical_return_tests_run": 0,
        "frozen_stocklens8_changed": False,
        "synthetic_tqqq_returns_used": False,
        "broker_orders_authorized": False,
        "capital_deployment_authorized": False,
        "automatic_promotion": False,
    }


if __name__ == "__main__":
    print(json.dumps(audit_year(2026), sort_keys=True, indent=2))

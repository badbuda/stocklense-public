"""Synthetic chronology tests; no externally witnessed first-seen receipts."""
import pytest
from research_cross_calendar_gate import (
    audit_year, next_equity_open_after, sec_dissemination_lower_bound,
)


def filing(form, local_time, accepted=None):
    # October 9, 2026 is EDT (UTC-04); tests intentionally use explicit offsets.
    t = local_time + "-04:00"
    return sec_dissemination_lower_bound(
        form=form, transmission_started_at_utc=t,
        accepted_at_utc=(accepted or t),
    )


def test_2026_two_equity_open_federal_holiday_collisions():
    x = audit_year(2026)
    assert x["xnys_sessions"] == 251
    assert x["observed_federal_holidays"] == 11
    assert x["xnys_open_federal_holidays"] == ["2026-10-12", "2026-11-11"]
    assert x["independently_qualified_pit_rows"] == 0
    assert not x["capital_deployment_authorized"]


def test_october_9_late_8k_cannot_be_same_day_and_skips_federal_holiday():
    x = filing("8-K", "2026-10-09T17:31:00")
    assert x["earliest_possible_date"] == "2026-10-13"
    assert x["after_1730_et"] and not x["published_form_exception"]
    assert not x["actual_public_first_seen_verified"]


def test_late_exception_form4_is_not_deferred_by_rule_but_still_not_proven():
    x = filing("4", "2026-10-09T21:59:00")
    assert x["earliest_possible_date"] == "2026-10-09"
    assert x["published_form_exception"]
    assert not x["tradable_event_qualified"]


def test_regular_filing_before_cutoff_is_same_day_possible_not_certified():
    x = filing("10-Q", "2026-10-09T17:29:59")
    assert x["earliest_possible_date"] == "2026-10-09"
    assert not x["tradable_event_qualified"]


@pytest.mark.parametrize("started", [
    "2026-10-12T12:00:00-04:00",  # Federal holiday, equity market OPEN
    "2026-10-10T12:00:00-04:00",  # Saturday
    "2026-10-09T05:59:59-04:00",  # before EDGAR window
    "2026-10-09T22:00:00-04:00",  # at close
])
def test_no_false_sec_operating_day(started):
    with pytest.raises(ValueError):
        sec_dissemination_lower_bound(
            form="8-K", transmission_started_at_utc=started,
            accepted_at_utc=started,
        )


def test_acceptance_must_not_precede_transmission():
    with pytest.raises(ValueError, match="ACCEPTED_BEFORE_TRANSMISSION"):
        filing("8-K", "2026-10-09T17:31:00", "2026-10-09T17:30:00-04:00")


@pytest.mark.parametrize("bad", ["2026-10-09T17:31:00", "not-a-date", ""])
def test_naive_or_malformed_receipt_rejected(bad):
    with pytest.raises(ValueError):
        sec_dissemination_lower_bound(
            form="8-K", transmission_started_at_utc=bad,
            accepted_at_utc="2026-10-09T21:31:00Z",
        )


def test_next_xnys_open_after_utc_receipt_respects_holiday_collision():
    # Friday post-close -> Monday Oct 12 equity open, even though SEC is shut.
    assert next_equity_open_after("2026-10-09T22:00:00Z") == "2026-10-12T13:30:00+00:00"
    # On the open itself, strictly future open is Tuesday.
    assert next_equity_open_after("2026-10-12T13:30:00Z") == "2026-10-13T13:30:00+00:00"


def test_us_dst_fall_back_open_is_1430z():
    assert next_equity_open_after("2026-11-01T14:00:00Z") == "2026-11-02T14:30:00+00:00"


def test_late_exception_accepted_after_22_cannot_claim_same_day():
    x = filing("4", "2026-10-09T21:59:00", "2026-10-09T22:01:00-04:00")
    assert x["earliest_possible_date"] == "2026-10-13"
    assert not x["actual_public_first_seen_verified"]


def test_before_cutoff_but_next_day_acceptance_not_backdated():
    x = filing("10-Q", "2026-10-09T17:29:59", "2026-10-13T06:00:00-04:00")
    assert x["earliest_possible_date"] == "2026-10-13"


def test_committed_calendar_result_matches_code_and_has_no_capital_flag():
    import json
    from pathlib import Path
    p = Path(__file__).resolve().parents[1] / "research/results/sl9_030_cross_calendar_2026.json"
    data = json.loads(p.read_text())
    assert data == audit_year(2026)
    assert data["historical_return_tests_run"] == 0
    assert data["broker_orders_authorized"] is False

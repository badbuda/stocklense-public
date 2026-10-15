"""Adversarial synthetic clocks only; no historical first-seen certification."""
from hashlib import sha256
import json
import pytest
from research_pit_decision_join import (
    decision_0931, macro_candidate, sec_candidate, gdelt_candidate,
    quote_capacity_candidate,
)

DECISION = "2026-10-15T13:31:00Z"

def macro(vintage="2026-10-14", latest="0.91"):
    return json.dumps({"series_id": "T10Y3M", "response": {
        "realtime_start": vintage, "realtime_end": vintage,
        "observation_start": "2026-10-09", "observation_end": vintage,
        "units": "lin", "output_type": 1, "file_type": "json",
        "order_by": "observation_date", "sort_order": "asc",
        "count": 2, "offset": 0, "limit": 100000,
        "observations": [
            {"date": "2026-10-09", "realtime_start": vintage,
             "realtime_end": vintage, "value": "0.99"},
            {"date": vintage, "realtime_start": vintage,
             "realtime_end": vintage, "value": latest}
        ]}}, sort_keys=True).encode()

def test_macro_candidate_does_not_certify():
    raw = macro()
    r = macro_candidate(raw, series_id="T10Y3M", decision_at_utc=DECISION,
        collector_received_at_utc="2026-10-14T23:00:00Z", claimed_first_seen=True)
    assert r["raw_sha256"] == sha256(raw).hexdigest()
    assert r["qualified_rows"] == 0 and r["claimed_first_seen_ignored"]
    assert not r["independent_first_seen_proven"]
    assert r["status"] == "BLOCKED_NO_INDEPENDENT_RELEASE_CLOCK"

def test_latest_missing_never_carried_forward():
    r = macro_candidate(macro(latest="."), series_id="T10Y3M",
        decision_at_utc=DECISION, collector_received_at_utc="2026-10-14T23:00:00Z")
    assert r["latest_missing"] and r["status"] == "BLOCKED_MISSING_LATEST_VALUE"

@pytest.mark.parametrize("received,decision,error", [
    ("2026-10-15T13:31:00Z", DECISION, "RECEIPT_NOT_BEFORE_DECISION"),
    ("2026-10-15T13:32:00Z", DECISION, "RECEIPT_NOT_BEFORE_DECISION"),
    ("2026-10-13T23:00:00Z", DECISION, "RECEIPT_BEFORE_CLAIMED_VINTAGE"),
    ("2026-10-14T23:00:00Z", "2026-10-17T13:31:00Z", "DECISION_NOT_XNYS_SESSION"),
    ("2026-10-14T23:00:00Z", "2026-10-15T13:30:59Z", "DECISION_NOT_0931_ET"),
    ("2026-10-14T23:00:00Z", "2026-10-15T13:32:00Z", "DECISION_NOT_0931_ET"),
])
def test_macro_chronology_rejections(received, decision, error):
    with pytest.raises(ValueError, match=error):
        macro_candidate(macro(), series_id="T10Y3M",
            decision_at_utc=decision, collector_received_at_utc=received)

def test_future_vintage_and_wrong_series_rejected():
    with pytest.raises(ValueError, match="future or multi-day"):
        macro_candidate(macro(vintage="2026-10-15"), series_id="T10Y3M",
            decision_at_utc=DECISION, collector_received_at_utc="2026-10-15T13:30:00Z")
    with pytest.raises(ValueError, match="wrong pinned series"):
        macro_candidate(macro(), series_id="BAMLH0A0HYM2",
            decision_at_utc=DECISION, collector_received_at_utc="2026-10-14T23:00:00Z")

def sec(**change):
    args = dict(form="8-K",
        started_at_utc="2026-10-09T17:31:00-04:00",
        accepted_at_utc="2026-10-09T17:32:00-04:00",
        collector_received_at_utc="2026-10-13T13:00:00Z",
        decision_at_utc="2026-10-13T13:31:00Z", claimed_first_seen=True)
    args.update(change)
    return sec_candidate(**args)

def test_late_8k_cannot_backdate_to_equity_open_federal_holiday():
    with pytest.raises(ValueError, match="SEC_RECEIPT_BEFORE_EARLIEST_PUBLIC_DAY"):
        sec(collector_received_at_utc="2026-10-12T13:00:00Z",
            decision_at_utc="2026-10-12T13:31:00Z")

def test_sec_candidate_only_and_s_bmef_late_exception():
    x = sec()
    assert x["earliest_possible_date"] == "2026-10-13"
    assert x["qualified_rows"] == 0 and x["claimed_first_seen_ignored"]
    y = sec(form="S-BMEF",
        started_at_utc="2026-10-09T21:58:00-04:00",
        accepted_at_utc="2026-10-09T21:59:00-04:00",
        collector_received_at_utc="2026-10-10T02:00:00Z",
        decision_at_utc="2026-10-12T13:31:00Z")
    assert y["earliest_possible_date"] == "2026-10-09"
    assert y["qualified_rows"] == 0

@pytest.mark.parametrize("change,error", [
    ({"collector_received_at_utc":"2026-10-09T21:31:30Z"}, "SEC_RECEIPT_BEFORE_ACCEPTANCE"),
    ({"collector_received_at_utc":"2026-10-13T13:31:00Z"}, "RECEIPT_NOT_BEFORE_DECISION"),
    ({"accepted_at_utc":"2026-10-09T17:30:00-04:00"}, "ACCEPTED_BEFORE_TRANSMISSION"),
])
def test_sec_rejects_bad_chronology(change,error):
    with pytest.raises(ValueError, match=error):
        sec(**change)

def gdelt(**change):
    args = dict(article_published_at_utc="2026-10-09T18:00:00Z",
        batch_at_utc="2026-10-13T12:45:00Z",
        collector_received_at_utc="2026-10-13T13:00:00Z",
        decision_at_utc="2026-10-13T13:31:00Z", claimed_first_seen=True)
    args.update(change)
    return gdelt_candidate(**args)

def test_gdelt_batch_not_article_clock_and_never_certified():
    x = gdelt()
    assert x["qualified_rows"] == 0 and x["claimed_first_seen_ignored"]
    assert not x["article_time_used_as_first_seen"]
    with pytest.raises(ValueError, match="RECEIPT_NOT_BEFORE_DECISION"):
        gdelt(decision_at_utc="2026-10-12T13:31:00Z")
    with pytest.raises(ValueError, match="GDELT_BATCH_BEFORE_ARTICLE"):
        gdelt(article_published_at_utc="2026-10-13T13:00:00Z")
    with pytest.raises(ValueError, match="GDELT_RECEIPT_BEFORE_BATCH"):
        gdelt(collector_received_at_utc="2026-10-13T12:44:00Z")

def quote(**patch):
    q = dict(symbol="TQQQ", source_type="NBBO", quote_condition="REGULAR",
        source_record_sha256=sha256(b"synthetic").hexdigest(),
        timestamp_utc="2026-10-15T13:30:59.750Z",
        bid=25.01, ask=25.02, bid_size=80, ask_size=90)
    q.update(patch)
    return q

def test_quote_depth_is_only_hypothetical():
    x = quote_capacity_candidate(quote=quote(), side="BUY",
        shares=100, decision_at_utc=DECISION)
    assert x["hypothetical_shares_at_one_displayed_quote"] == 90
    assert not x["displayed_size_covers_request"]
    assert x["quote_age_ms"] == 250
    assert x["actual_broker_fills_verified"] == 0
    y = quote_capacity_candidate(quote=quote(), side="SELL",
        shares=40, decision_at_utc=DECISION)
    assert y["hypothetical_shares_at_one_displayed_quote"] == 40
    assert y["actual_broker_fills_verified"] == 0

@pytest.mark.parametrize("patch,shares,side,error", [
    ({"timestamp_utc":"2026-10-15T13:30:58Z"},1,"BUY","NBBO_FUTURE_OR_STALE"),
    ({"timestamp_utc":"2026-10-15T13:31:01Z"},1,"BUY","NBBO_FUTURE_OR_STALE"),
    ({"ask":24.99},1,"BUY","crossed quote"),
    ({"quote_condition":"HALTED"},1,"BUY","not a regular NBBO"),
    ({},0,"BUY","INVALID_HYPOTHETICAL_ORDER"),
    ({},True,"BUY","INVALID_HYPOTHETICAL_ORDER"),
    ({},1,"SHORT","INVALID_HYPOTHETICAL_ORDER"),
])
def test_quote_fails_closed(patch,shares,side,error):
    with pytest.raises(ValueError, match=error):
        quote_capacity_candidate(quote=quote(**patch),side=side,
            shares=shares,decision_at_utc=DECISION)

def test_dst_and_federal_holiday_equity_open():
    t,day=decision_0931("2026-11-11T14:31:00Z")
    assert day=="2026-11-11"
    with pytest.raises(ValueError,match="DECISION_NOT_0931_ET"):
        decision_0931("2026-11-11T13:31:00Z")

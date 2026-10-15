"""Synthetic quotes only; no actual NBBO entitlement or broker fill."""
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import hashlib,json
import pytest
from research_pit_quote_gate import audit

def raw(x):return json.dumps(x,sort_keys=True).encode()

def quote(day="2026-10-09",minute=31):
    stamp=datetime.fromisoformat(day).replace(hour=9,minute=minute,
               tzinfo=ZoneInfo("America/New_York")).astimezone(timezone.utc)
    return {"symbol":"TQQQ","source_type":"NBBO",
        "quote_condition":"REGULAR",
        "source_record_sha256":hashlib.sha256(b"synthetic").hexdigest(),
        "timestamp_utc":stamp.isoformat(),
        "bid":25.01,"ask":25.02,"bid_size":100,"ask_size":150,
        "independently_verified":True,"broker_fill_observed":True}

def test_dst_and_self_asserted_proof_do_not_qualify_quotes():
    x=audit(raw([quote("2026-03-09"),quote("2026-10-09")]))
    assert x["syntactically_valid_quote_rows"]==2
    assert x["session_labels"]==2
    assert x["independently_qualified_nbbo_rows"]==0
    assert x["broker_fills_observed"] is False
    assert x["capital_authorized"] is False

@pytest.mark.parametrize("patch,error",[
    ({"bid":25.03},"crossed quote"),
    ({"ask":0},"invalid bid or ask"),
    ({"bid":True},"invalid bid or ask"),
    ({"bid_size":0},"invalid quote sizes"),
    ({"source_type":"DAILY_OPEN"},"not a regular NBBO"),
    ({"quote_condition":"HALTED"},"not a regular NBBO"),
    ({"source_record_sha256":"oops"},"invalid quote hash"),
    ({"timestamp_utc":"2026-10-09T09:31:00"},"naive quote time")])
def test_invalid_quote_fail_closed(patch,error):
    x=quote();x.update(patch)
    with pytest.raises(ValueError,match=error):audit(raw([x]))

def test_holiday_window_and_duplicate_fail_closed():
    with pytest.raises(ValueError,match="not an XNYS session"):
        audit(raw([quote("2026-10-10")]))
    with pytest.raises(ValueError,match="not opening"):
        audit(raw([quote(minute=40)]))
    with pytest.raises(ValueError,match="duplicate quote time"):
        audit(raw([quote(),quote()]))

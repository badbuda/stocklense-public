import copy
from datetime import datetime,timezone
import pytest
from frozen_forward_evidence_contract import build_record,validate,verify
H="a"*64

def missed(day,reason="collector unavailable"):
    return {"schema_version":1,"model":"STOCKLENS_8_0_FROZEN",
    "session_date":day,"status":"MISSED","broker_orders_authorized":False,
    "missing_reason":reason,"external_server_receipt":None,"market_source":None}

def good(day="2026-10-09"):
    return {"schema_version":1,"model":"STOCKLENS_8_0_FROZEN",
    "session_date":day,"status":"COMPLETE","broker_orders_authorized":False,
    "external_server_receipt":{"verified_external_append_only":True,
       "server":"EXTERNAL_WORM_STORE","signed_proof_id":"independent-capture-123",
       "received_at_utc":"2026-10-09T20:30:00Z"},
    "market_source":{"qqq_kind":"OBSERVED_REAL_ETF","tqqq_kind":"OBSERVED_REAL_ETF",
       "qqq_raw_sha256":H,"tqqq_raw_sha256":H},
    "signal":{"core_sha256":H,"prior_input_sha256":H,"signal_sha256":H,
       "signal_asof_date":"2026-10-08",
       "external_preopen_received_utc":"2026-10-09T12:00:00Z"}}

def test_missed_requires_reason_and_is_not_data_backfill():
    r=build_record(missed("2026-10-08"))
    assert verify([r])["missed"]==1
    q=missed("2026-10-08","")
    with pytest.raises(ValueError,match="WITHOUT_REASON"):build_record(q)
    q=missed("2026-10-08");q["market_source"]={}
    with pytest.raises(ValueError,match="BACKFILL"):build_record(q)

def test_valid_daily_proof_is_schema_only_not_remote_certificate():
    rec=build_record(good())
    assert verify([rec])["capital_authorized"] is False
    assert verify([rec])["independent_external_verification_performed"] is False

def test_cannot_build_fake_unsigned_or_synthetic_close():
    x=good();x["external_server_receipt"]["verified_external_append_only"]=False
    with pytest.raises(ValueError,match="NOT_INDEPENDENTLY"):build_record(x)
    x=good();x["market_source"]["tqqq_kind"]="QQQ_TIMES_THREE"
    with pytest.raises(ValueError,match="SYNTHETIC"):build_record(x)

def test_preopen_timestamp_is_required_and_no_future_signal():
    x=good();x["signal"]["external_preopen_received_utc"]="2026-10-09T14:00:00Z"
    with pytest.raises(ValueError,match="AFTER_OPEN"):build_record(x)
    x=good();x["signal"]["signal_asof_date"]="2026-10-09"
    with pytest.raises(ValueError,match="FUTURE_SIGNAL"):build_record(x)

def test_calendar_chain_cannot_hide_missing_sessions():
    a=build_record(missed("2026-10-07"))
    with pytest.raises(ValueError,match="GAP_WITHOUT_MISSED"):
        build_record(good("2026-10-09"),a)
    b=build_record(missed("2026-10-08"),a)
    c=build_record(good(),b)
    assert verify([a,b,c])["records"]==3

def test_mutation_of_old_record_detected():
    x=build_record(missed("2026-10-08"))
    y=copy.deepcopy(x);y["missing_reason"]="tampered"
    with pytest.raises(ValueError,match="HASH_TAMPERING"):validate(y)

def test_weekend_rejected():
    with pytest.raises(ValueError,match="NOT_XNYS"):build_record(missed("2026-10-10"))

def test_complete_receipt_must_be_after_actual_session_close():
    x=good()
    x["external_server_receipt"]["received_at_utc"]="2026-10-09T14:15:00Z"
    with pytest.raises(ValueError,match="PRE_SESSION_CLOSE"):
        build_record(x)


@pytest.mark.parametrize("bad_asof,code", [
    (None,"INVALID_SIGNAL_ASOF"),
    ("garbage","INVALID_SIGNAL_ASOF"),
    ("2026-10-09","FUTURE_SIGNAL"),
    ("2026-10-07","NOT_PREVIOUS_XNYS_SESSION"),
])
def test_complete_signal_must_be_from_prior_completed_xnys_session(bad_asof,code):
    x=good()
    x["signal"]["signal_asof_date"]=bad_asof
    with pytest.raises(ValueError,match=code):
        build_record(x)


def test_actual_dst_session_open_is_used_not_fixed_utc_offset():
    x=good()
    # 13:31 UTC on a summer DST session is after the 09:30 ET open.
    x["signal"]["external_preopen_received_utc"]="2026-10-09T13:31:00Z"
    with pytest.raises(ValueError,match="AFTER_OPEN"):
        build_record(x)

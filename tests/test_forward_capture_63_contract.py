import copy
import pytest
from forward_capture_63_contract import check,sha256,ZERO


def prereg():
    return {"schema_version":1,"candidate":"StockLens 8.0 FROZEN","no_synthetic_etf":True,
        "external_attestor_proven":False,"deployment_status":"NOT_DEPLOYED",
        "broker_order_execution_authorized":False,
        "frozen_core_git_blob_sha":"258c6918ea10456754bcd26f782af77545a56b2b",
        "earliest_capture_session":"2026-10-12"}


def first():
    r={"schema_version":1,"session_date":"2026-10-12","status":"COMPLETE",
       "recorded_at_utc":"2026-10-12T22:00:00+00:00",
       "prior_record_sha256":ZERO,"broker_orders_authorized":False,
       "broker_fills_observed":False,"synthetic_etf_prices_used":False,
       "independent_vendor_receipt_proven":False,
       "signal":{"core_git_blob_sha":prereg()["frozen_core_git_blob_sha"],
                 "target_leverage":3,"asof_date":"2026-10-09",
                 "created_at_utc":"2026-10-12T12:00:00+00:00"},
       "market":{"source_kind":"OBSERVED_ACTUAL_QQQ_TQQQ_ETF",
          "synthetic_etf":False,
          "raw_response_sha256":{"QQQ":"a"*64,"TQQQ":"b"*64}},
       "nav_usd":99999.}
    r["record_sha256"]=sha256({k:v for k,v in r.items() if k!="record_sha256"})
    return r


def test_no_existing_archive_counts_as_actual_forward():
    x=check([],prereg())
    assert x["independently_attested_forward_sessions"]==0
    assert not x["63_session_capture_gate_passed"]


def test_even_one_locally_consistent_record_cannot_self_attest():
    x=check([first()],prereg(),expected_through="2026-10-12")
    assert x["complete_modeled_etf_sessions"]==1
    assert x["independently_attested_forward_sessions"]==0
    assert x["capital_deployment_authorized"] is False


def test_future_leakage_refused_even_with_matching_hash():
    r=first();r["signal"]["created_at_utc"]="2026-10-12T18:00:00Z"
    r["record_sha256"]=sha256({k:v for k,v in r.items() if k!="record_sha256"})
    with pytest.raises(ValueError,match="FORWARD_SIGNAL_AFTER_MARKET_OPEN"):
        check([r],prereg())


def test_missed_cannot_be_backfilled_or_claim_nav():
    r=first();r["status"]="MISSED";r["miss_reason"]="provider_unavailable"
    r["signal"]=None;r["nav_usd"]=10.
    r["record_sha256"]=sha256({k:v for k,v in r.items() if k!="record_sha256"})
    with pytest.raises(ValueError,match="FORWARD_MISSED_SESSION_CANNOT"):
        check([r],prereg())


def test_missing_exchange_day_not_silently_allowed():
    with pytest.raises(ValueError,match="FORWARD_MISSING_OR_NON_EXCHANGE"):
        check([],prereg(),expected_through="2026-10-12")


def test_hash_chain_tampering_rejected():
    r=first();r["nav_usd"]=1.
    with pytest.raises(ValueError,match="FORWARD_RECORD_SHA_INVALID"):
        check([r],prereg())


def test_forged_independent_receipt_flag_refused():
    r=first();r["independent_vendor_receipt_proven"]=True
    r["record_sha256"]=sha256({k:v for k,v in r.items() if k!="record_sha256"})
    with pytest.raises(ValueError,match="FORWARD_UNSUPPORTED_EXTERNAL_EVIDENCE_CLAIM"):
        check([r],prereg())

def test_missing_security_flags_are_not_assumed_false():
    row=first()
    del row["independent_vendor_receipt_proven"]
    row["record_sha256"]=sha256({k:v for k,v in row.items() if k!="record_sha256"})
    with pytest.raises(ValueError,match="FORWARD_UNSUPPORTED_EXTERNAL_EVIDENCE_CLAIM"):
        check([row],prereg())


def test_cannot_timestamp_a_record_before_signal():
    row=first()
    row["recorded_at_utc"]="2026-10-12T11:00:00Z"
    row["record_sha256"]=sha256({k:v for k,v in row.items() if k!="record_sha256"})
    with pytest.raises(ValueError,match="FORWARD_RECORD_PREDATES_SIGNAL"):
        check([row],prereg())

"""Regression: native QC simulation quotes are not independent NBBO or broker fills."""
import hashlib
import json
from pathlib import Path

import pytest

from qc_native_original_execution_forensics import evaluate, audit_file, PINNED_SL724_SHA256


def fixture():
    def order(i,symbol,side,fill,bid,ask,last,when):
        return {"id":i,"status":3,"symbol":{"value":symbol},
                "quantity":100 if side=="BUY" else -100,"price":fill,
                "orderSubmissionData":{"bidPrice":bid,"askPrice":ask,"lastPrice":last},
                "time":when}
    return {
        "charts":{"SL724":{"series":{
            "Leverage":{"values":[[1,3.],[2,2.],[3,3.]]},
            "NAV":{"values":[[1,1.],[2,1.05],[3,1.1]]},
            "Drawdown":{"values":[[1,0],[2,-1],[3,0]]}}}},
        "orders":{
          "1":order(1,"TQQQ","BUY",101.,100.,100.5,100.1,"2020-03-03T14:32:00Z"),
          "2":order(2,"QQQ","SELL",100.,100.,100.5,100.2,"2020-03-04T14:31:00Z"),
        },
    }


def payload(obj):
    raw=json.dumps(obj,sort_keys=True).encode()
    return raw,hashlib.sha256(raw).hexdigest()


def test_synthetic_reference_never_spoofs_pinned_original():
    source=fixture()
    raw,sha=payload(source)
    report=evaluate(source,raw,expected_sha=sha)
    assert report["status"]=="SYNTHETIC_TEST_FIXTURE_NOT_ORIGINAL"
    assert not report["source_original_sha256_matched"]
    assert not report["actual_broker_fills_observed"]
    assert not report["independent_executable_NBBO_verified"]
    assert not report["automatic_live_trading_authorized"]
    assert report["native_order_count"]==2
    assert report["statistics_by_security"]["TQQQ"]["simulated_orders"]==1
    assert report["statistics_by_security"]["QQQ"]["simulated_orders"]==1
    assert report["statistics_by_security"]["ALL"]["simulated_orders"]==2
    assert PINNED_SL724_SHA256!=sha


def test_original_source_hash_required_without_test_override():
    source=fixture()
    raw,sha=payload(source)
    with pytest.raises(ValueError,match="ORIGINAL_SOURCE_NOT_LOCKED"):
        evaluate(source,raw)
    with pytest.raises(ValueError,match="LOCKED_ORIGINAL_SOURCE_SHA256_MISMATCH"):
        evaluate(source,raw,expected_sha="0"*64)


@pytest.mark.parametrize("mutation,reason",[
    (lambda x:x["orders"]["1"].pop("orderSubmissionData"),"NATIVE_SUBMISSION_QUOTE_MISSING"),
    (lambda x:x["orders"]["1"].update(status=2),"NOT_FILLED_ORIGINAL_ORDER"),
    (lambda x:x["orders"]["1"].update(price=0),"INVALID_SIMULATED_FILL_PRICE"),
    (lambda x:x["orders"]["1"]["orderSubmissionData"].update(bidPrice=102.),"SIMULATED_CROSSED_BID_ASK"),
    (lambda x:x["orders"]["1"].update(quantity=0),"INVALID_ORDER_QUANTITY"),
    (lambda x:x["orders"]["1"].update(time="2020-03-03T14:32:00"),"INVALID_ORDER_UTC_TIMESTAMP"),
    (lambda x:x["orders"]["1"].update(id=18),"NATIVE_ORDER_ID_MISMATCH"),
    (lambda x:x["charts"]["SL724"]["series"]["NAV"].update(values=[[1,1.]]),"SL724_CHART_LENGTH_DRIFT"),
])
def test_reject_simulated_fill_quote_inconsistencies(mutation,reason):
    source=fixture()
    mutation(source)
    raw,sha=payload(source)
    with pytest.raises(ValueError,match=reason):
        evaluate(source,raw,expected_sha=sha)


def test_detect_native_outlier_but_never_call_it_market_slippage():
    s=fixture()
    s["orders"]["1"]["price"]=103.
    raw,sha=payload(s)
    out=evaluate(s,raw,expected_sha=sha)
    assert out["outlier_50bps_any_diagnostic_count"]>=1
    assert out["outlier_records_aggregated_no_private_order_identity"]
    assert "order_id" not in out["outlier_records_aggregated_no_private_order_identity"][0]
    assert out["actual_broker_fills_observed"] is False


def test_local_private_aggregate_not_raw_order_dump(tmp_path):
    original=fixture()
    private=tmp_path/"private_original.json"
    private.write_text(json.dumps(original))
    digest=hashlib.sha256(private.read_bytes()).hexdigest()
    report=audit_file(private,expected_sha=digest,out=tmp_path/"aggregate.json")
    parsed=json.loads((tmp_path/"aggregate.json").read_text())
    assert parsed==report
    assert "orders" not in parsed
    assert "brokerId" not in json.dumps(parsed)
    assert parsed["independent_executable_NBBO_verified"] is False

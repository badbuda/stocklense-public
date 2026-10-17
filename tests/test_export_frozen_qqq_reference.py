from datetime import datetime
import csv,io
import pytest
from export_frozen_qqq_reference import reference_csv

def test_export_reference_requires_exact_session_and_pinned_vendor():
    frame={"Date":[datetime(2008,1,2),datetime(2008,1,3)],
           "Close":[100.001,100.002]}
    audit={"source":"YFINANCE_QQQ_AUTO_ADJUSTED"}
    raw,info=reference_csv(frame,audit,"2008-01-03")
    assert list(csv.DictReader(io.StringIO(raw.decode())))[-1]["Close"]=="100.002"
    assert info["independent_vendor_proven"] is False
    assert info["broker_actions"] is False
    with pytest.raises(ValueError,match="NOT_COMPLETE"):
        reference_csv(frame,audit,"2008-01-04")
    with pytest.raises(ValueError,match="SOURCE_NOT_PROVEN"):
        reference_csv(frame,{"source":"UNVERIFIED"},"2008-01-03")

def test_duplicate_and_nonfinite_frozen_history_denied():
    audit={"source":"YFINANCE_QQQ_AUTO_ADJUSTED"}
    with pytest.raises(ValueError,match="NOT_COMPLETE"):
        reference_csv({"Date":[datetime(2008,1,2)]*2,
                       "Close":[100.0,100.1]},audit,"2008-01-02")
    with pytest.raises(ValueError,match="INVALID_CLOSE"):
        reference_csv({"Date":[datetime(2008,1,2),datetime(2008,1,3)],
                       "Close":[100.0,float("nan")]},audit,"2008-01-03")

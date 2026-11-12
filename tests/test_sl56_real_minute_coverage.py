"""Pure offline source-qualification regression. No Alpaca/AWS/broker calls."""
from datetime import datetime, timedelta, timezone
import json

import pytest
from stocklens.paper_minute_coverage import (
    MinuteCoverageError, audit_one, audit_pair,
)
from infra.aws.sl56_alpaca_historical_minutes_readonly import fetch_symbol

START = datetime(2026,11,5,14,30,tzinfo=timezone.utc)


def bars(n=390):
    return [{
        "t": (START + timedelta(minutes=i)).isoformat().replace("+00:00", "Z"),
        "o": 500.0 + i/100,
        "h": 500.4 + i/100,
        "l": 499.6 + i/100,
        "c": 500.1 + i/100,
        "v": 50000,
    } for i in range(n)]


def test_true_390_observed_minutes_are_research_only_not_paper_permission():
    result = audit_pair({"QQQ":bars(),"TQQQ":bars()}, "2026-11-05")
    assert result["status"] == "RESEARCH_PAIR_COMPLETE_NOT_EXECUTION_AUTHORIZATION"
    assert result["paper_receipts_written"] is False
    assert result["historical_missed_sessions_requalified"] is False
    assert result["broker_orders_authorized"] is False
    assert all(x["observed_regular_minute_bars"] == 390 and
               x["required_minimum_bars"] == 385 and
               x["source_entitlement_proven_by_response"] is False
               for x in result["per_symbol"].values())


def test_incident_289_is_refused_no_fake_close_or_execution():
    data = bars()[101:]
    r = audit_pair({"QQQ":data,"TQQQ":bars()}, "2026-11-05")
    assert r["status"] == "RESEARCH_PAIR_INCOMPLETE_NO_PAPER"
    q = r["per_symbol"]["QQQ"]
    assert q["observed_regular_minute_bars"] == 289
    assert q["required_minimum_bars"] == 385
    assert q["missing_regular_minute_bars"] == 101
    assert q["observed_0931"] is False


def test_gaps_up_to_five_are_allowed_only_when_open_and_real_close_present():
    complete = bars()
    removed = {41,62,83,104,125}
    accept = [v for i,v in enumerate(complete) if i not in removed]
    assert audit_one("QQQ",accept,"2026-11-05")["status"] == (
        "COMPLETE_OBSERVED_MINUTES_RESEARCH_ONLY")
    with_missing_open=[v for i,v in enumerate(complete) if i!=1]
    assert audit_one("QQQ",with_missing_open,"2026-11-05")["status"] == (
        "INCOMPLETE_OBSERVED_MINUTES_NO_PAPER")
    with_missing_final=[v for i,v in enumerate(complete) if i!=389]
    assert audit_one("QQQ",with_missing_final,"2026-11-05")["status"] == (
        "INCOMPLETE_OBSERVED_MINUTES_NO_PAPER")


def test_duplicate_price_bar_or_bad_price_is_not_accepted():
    source=bars()
    with pytest.raises(MinuteCoverageError,match="DUPLICATE"):
        audit_one("QQQ",source+[source[20]],"2026-11-05")
    broken=bars()
    broken[60]["c"]=-1
    with pytest.raises(MinuteCoverageError,match="INVALID_BAR_OHLC"):
        audit_one("QQQ",broken,"2026-11-05")


def test_pair_must_have_both_real_etfs():
    with pytest.raises(MinuteCoverageError,match="REQUIRE_QQQ_AND_TQQQ_PAIR"):
        audit_pair({"QQQ":bars()}, "2026-11-05")


def test_readonly_alpaca_probe_pins_sip_1m_raw_and_no_order_api():
    class MockResponse:
        def __init__(self,raw):self.raw=raw
        def __enter__(self):return self
        def __exit__(self,*a):return False
        def read(self,size):return self.raw
    calls=[]
    data=bars()
    def fake_open(req,timeout):
        calls.append(req)
        assert req.method=="GET"
        assert req.full_url.startswith("https://data.alpaca.markets/v2/stocks/bars?")
        assert "feed=sip" in req.full_url and "timeframe=1Min" in req.full_url
        assert "adjustment=raw" in req.full_url
        return MockResponse(json.dumps({"bars":{"QQQ":data},"next_page_token":None}).encode())
    outcome=fetch_symbol("QQQ","2026-11-05",key="fixture-key",
                         secret="fixture-secret",opener=fake_open)
    assert len(outcome)==390
    assert len(calls)==1


def test_source_has_no_broker_aws_or_mutating_calls():
    from pathlib import Path
    src=Path("infra/aws/sl56_alpaca_historical_minutes_readonly.py").read_text()
    for forbidden in ("boto3", "lambda.invoke", "s3.put_object",
                      "place_order(", "submit_order(", "POST", "requests.post"):
        assert forbidden not in src
    assert "ALPACA_HISTORICAL_READONLY_CREDENTIALS_REQUIRED" in src
    assert "source_entitlement_proven_by_response" in Path(
        "stocklens/paper_minute_coverage.py").read_text()

"""Synthetic fixtures; passing tests never establish historical investment alpha."""
import hashlib,json
import pytest
from research_pit_credit_gate import fred
from research_pit_event_gate import audit as events

def b(x):return json.dumps(x,sort_keys=True).encode()
def sha():return hashlib.sha256(b"fixture").hexdigest()

def series():
    return {"series_id":"BAMLH0A0HYM2","offset":0,"count":2,
        "observations":[
            {"date":"2018-02-05","realtime_start":"2018-02-06",
             "realtime_end":"2018-02-08","value":"3.20"},
            {"date":"2018-02-05","realtime_start":"2018-02-09",
             "realtime_end":"9999-12-31","value":"3.40"}]}

def event(provider="SEC_EDGAR"):
    x={"provider":provider,"source_record_id":"test","source_record_sha256":sha(),
       "published_at_utc":"2024-03-20T18:01:00Z",
       "collected_at_utc":"2024-03-20T18:04:00Z",
       "archived_first_seen_verified":True}
    if provider=="SEC_EDGAR":x["accepted_at_utc"]="2024-03-20T18:01:00Z"
    if provider.endswith("_SCHEDULE"):x["scheduled_release_at_utc"]="2024-03-21T18:00:00Z"
    return x

def test_alfred_vintage_date_is_not_trading_clock():
    x=fred(b(series()))
    assert x["rows"]==2 and x["distinct_vintage_starts"]==2
    assert x["pre2023_observations_with_pre2023_vintage"]==1
    assert x["licensed_h1_test"] is False
    assert x["independent_first_seen"] is False

@pytest.mark.parametrize("change,error",[
    ({"series_id":"DGS10"},"series not pinned"),
    ({"count":3},"incomplete observations"),
    ({"offset":1},"incomplete observations")])
def test_alfred_response_fail_closed(change,error):
    x=series();x.update(change)
    with pytest.raises(ValueError,match=error):fred(b(x))

@pytest.mark.parametrize("field,value,error",[
    ("realtime_start","2018-02-04","future observation"),
    ("realtime_end","2018-02-01","inverted vintage"),
    ("value","NaN","spread invalid"),
    ("value","-0.1","spread invalid"),
    ("date","2018-99-01","date invalid")])
def test_alfred_invalid_row(field,value,error):
    x=series();x["observations"][0][field]=value
    with pytest.raises(ValueError,match=error):fred(b(x))

def test_alfred_duplicate_and_missing_value():
    x=series();x["observations"].append(dict(x["observations"][0]));x["count"]=3
    with pytest.raises(ValueError,match="duplicate vintage"):fred(b(x))
    x=series();x["observations"][0]["value"]="."
    assert fred(b(x))["unique_observations"]==1

def test_sec_gdelt_fomc_cpi_do_not_self_certify():
    x=events(b([event("SEC_EDGAR"),event("GDELT_2_0_GKG"),
                event("FOMC_SCHEDULE"),event("BLS_CPI_SCHEDULE")]))
    assert x["metadata_rows"]==4 and x["qualified_tradable_event_rows"]==0
    assert x["sec_acceptance_equals_public_dissemination"] is False
    assert x["gdelt_batch_equals_article_first_seen"] is False

@pytest.mark.parametrize("patch,error",[
    ({"collected_at_utc":"2024-03-20T18:00:00Z"},"collection precedes"),
    ({"collected_at_utc":"2024-03-20T18:04:00"},"naive timestamp"),
    ({"accepted_at_utc":"2024-03-20T18:05:00Z"},"SEC accepted after"),
    ({"source_record_sha256":"x"},"invalid source hash")])
def test_event_bad_metadata(patch,error):
    x=event();x.update(patch)
    with pytest.raises(ValueError,match=error):events(b([x]))

def test_duplicate_and_future_result_leak():
    with pytest.raises(ValueError,match="duplicate event"):events(b([event(),event()]))
    x=event("FOMC_SCHEDULE");x["actual_value"]=0.25
    with pytest.raises(ValueError,match="calendar leaked outcome"):events(b([x]))

import json
import pytest
from datetime import date
from research_pit_credit_gate import fred

def test_overlapping_revision_ranges_rejected():
    a={"date":"2018-02-05","realtime_start":"2018-02-06",
       "realtime_end":"2018-02-10","value":"3.20"}
    b=dict(a,realtime_start="2018-02-09",
           realtime_end=date.max.isoformat(),value="3.40")
    raw=json.dumps({"series_id":"BAMLH0A0HYM2",
        "response":{"count":2,"offset":0,"observations":[a,b]}}).encode()
    with pytest.raises(ValueError,match="overlapping vintage intervals"):
        fred(raw)

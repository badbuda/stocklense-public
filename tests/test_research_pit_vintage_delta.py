import json
import pytest
from research_pit_vintage_delta import compare_vintages

def snap(v,values):
    rows=[dict(date=d,value=x,realtime_start=v,realtime_end=v) for d,x in values]
    return json.dumps(dict(series_id="T10Y3M",response=dict(
        realtime_start=v,realtime_end=v,observation_start="2026-10-09",
        observation_end="2026-10-14",units="lin",output_type=1,file_type="json",
        order_by="observation_date",sort_order="asc",count=len(rows),
        offset=0,limit=100000,observations=rows))).encode()

def test_delta_and_no_certification():
    a=snap("2026-10-13",[("2026-10-09","0.10"),("2026-10-12",".")])
    b=snap("2026-10-14",[("2026-10-09","0.11"),("2026-10-12","0.20"),("2026-10-13","0.15")])
    r=compare_vintages(a,b,series_id="T10Y3M",decision_session="2026-10-15")
    assert (r["revised_numeric_values"],r["filled_missing_values"],r["new_observations"])==(1,1,1)
    assert r["eligible_tradable_rows"]==0

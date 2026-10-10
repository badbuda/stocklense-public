"""Observer P0 Free chart: verified trailing session and unchanged original run economics."""
import json
from datetime import datetime,timezone
from pathlib import Path
from unittest.mock import patch

import pytest
from qc_chart_feature_acquisition import project,compare_original_rerun_invariants,FEATURES,CHART


def _ts(day):
    return int(datetime.fromisoformat(day+"T13:31:00+00:00").timestamp())


def fixture(tmp):
    dates=("2009-09-01","2009-09-02","2009-09-03")
    original=[{"date":d,"leverage":lev} for d,lev in zip(dates[:2],(3.0,2.0))]
    values={"close":[101.,102.,103.],"sma50":[90.,91.,92.],
            "sma200":[80.,81.,82.],"vol20":[.20,.21,.22],
            "mom12":[.15,.14,.13],"level":[3.,2.,3.],
            "defense":[0.,0.,0.]}
    original_series={"Leverage":{"values":[[_ts(d),lev] for d,lev in zip(dates[:2],(3,2))]},
        "NAV":{"values":[[_ts(d),1.0] for d in dates[:2]]},
        "Drawdown":{"values":[[_ts(d),0.0] for d in dates[:2]]}}
    run={"charts":{"SL724":{"series":original_series},
        CHART:{"series":{k:{"values":[[_ts(day),v] for day,v in zip(dates,vs)]}
           for k,vs in values.items()}}}}
    p=tmp/"diagnostic.json";p.write_text(json.dumps(run))
    return p,original,run


def test_accept_only_one_unambiguous_trailing_next_exchange_day(tmp_path):
    p, original,_=fixture(tmp_path)
    with patch("qc_chart_feature_acquisition.extract",return_value=(original,{"source_sha256":"original"})):
        rows,audit=project("original.json",p)
    assert len(rows)==2
    assert audit["diagnostic_series_sessions"]==3
    assert audit["excluded_trailing_feature_session"]=="2009-09-03"
    assert audit["excluded_trailing_sessions"]==1
    assert audit["all_original_sessions_compared_without_backfill"] is True
    assert audit["frozen_leverage_aligned_to_original"] is True
    assert audit["native_algorithm_source_identity_proven"] is False


@pytest.mark.parametrize("corrupt,expected",[
    ("extra_wrong_day","LEAN_DIAGNOSTIC_UNEXPECTED_TRAILING_SESSION"),
    ("extra_disagreement","LEAN_DIAGNOSTIC_UNEXPECTED_TRAILING_SESSION"),
    ("too_many","LEAN_DIAGNOSTIC_CHART_TRUNCATED_OR_WRONG_SESSION_COUNT"),
    ("missing_prior","LEAN_DIAGNOSTIC_FEATURE_DATES_DO_NOT_MATCH"),
    ("wrong_reference","LEAN_DIAGNOSTIC_CHANGED_FROZEN_LEVERAGE"),
    ("timestamp_drift","LEAN_DIAGNOSTIC_FEATURE_TIMESTAMPS_NOT_SYNCHRONIZED"),
])
def test_fail_closed_on_any_extra_or_unaligned_historical_session(tmp_path,corrupt,expected):
    p,original,obj=fixture(tmp_path)
    feat=obj["charts"][CHART]["series"]
    if corrupt=="extra_wrong_day":
        for f in FEATURES:feat[f]["values"][-1][0]=_ts("2009-09-08")
    elif corrupt=="extra_disagreement":
        feat["mom12"]["values"][-1][0]=_ts("2009-09-08")
    elif corrupt=="too_many":
        for f in FEATURES:feat[f]["values"].append([_ts("2009-09-04"),1.])
    elif corrupt=="missing_prior":
        for f in FEATURES:feat[f]["values"][1][0]=_ts("2009-09-03")
    elif corrupt=="wrong_reference":
        obj["charts"]["SL724"]["series"]["Leverage"]["values"][1][1]=3.
    elif corrupt=="timestamp_drift":
        feat["vol20"]["values"][1][0]+=-60
    p.write_text(json.dumps(obj))
    with patch("qc_chart_feature_acquisition.extract",return_value=(original,{"source_sha256":"original"})):
        with pytest.raises(ValueError,match=expected):
            project("original.json",p)


def test_native_orders_and_charts_strict_identity_ignore_only_closedtrade_guid(tmp_path):
    chart={"Leverage":{"values":[[1,3]]},"NAV":{"values":[[1,1]]},
           "Drawdown":{"values":[[1,0]]}}
    original={"charts":{"SL724":{"series":chart}},"orders":{"1":{"price":100}},
              "statistics":{"Compounding Annual Return":"12%"},
              "runtimeStatistics":{"Equity":"100"},
              "profitLoss":{"today":0},"rollingWindow":{},
              "totalPerformance":{"closedTrades":[{"id":"GUID-A","profitLoss":"50","orderIds":[1,2]}]}}
    copied=json.loads(json.dumps(original))
    copied["totalPerformance"]["closedTrades"][0]["id"]="GUID-B"
    copied["charts"]["SL724_P0_FEATURES"]={"series":{}}
    a=tmp_path/"original.json";b=tmp_path/"diag.json"
    a.write_text(json.dumps(original));b.write_text(json.dumps(copied))
    accepted=compare_original_rerun_invariants(a,b)
    assert accepted["native_execution_behavior_unchanged"] is True
    assert accepted["original_run_source_code_hash_attested"] is False
    assert accepted["independent_broker_quotes_proven"] is False
    copied["orders"]["1"]["price"]=102.
    b.write_text(json.dumps(copied))
    with pytest.raises(ValueError,match="LEAN_DIAGNOSTIC_CHANGED_ORIGINAL_RUN"):
        compare_original_rerun_invariants(a,b)

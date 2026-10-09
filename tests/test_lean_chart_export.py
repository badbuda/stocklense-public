"""Exercise chart transport with a simulated LEAN API, not live QuantConnect."""
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from integrations.lean_chart_feature_exporter import LeanChartFeatureExporter,CHART,COLUMNS
from qc_chart_feature_acquisition import project


class FakeLean:
    def __init__(self):
        self.plots=[]
    def plot(self,chart,key,value):
        self.plots.append((chart,key,value))


def test_chart_export_is_observational_and_seven_series_only():
    x=FakeLean();export=LeanChartFeatureExporter()
    export.record(x,close=100,sma50=90,sma200=80,vol20=.21,mom12=.1,level=3,defense=False)
    assert export.rows==1
    assert [k for chart,k,_ in x.plots]==list(COLUMNS)
    assert all(chart==CHART for chart,_,_ in x.plots)
    assert x.plots[-1]==(CHART,"defense",0.0)
    # Caller never receives any trade command, only plot transport.
    assert not hasattr(x,"MarketOrder")


def test_chart_export_rejects_nonfinite_values():
    with pytest.raises(ValueError,match="NONFINITE"):
        LeanChartFeatureExporter().record(
          FakeLean(),close=float("nan"),sma50=90,sma200=80,
          vol20=.2,mom12=.1,level=3,defense=False)


def fixture(tmp_path):
    date1="2009-09-01";date2="2009-09-02"
    original=[{"date":date1,"leverage":3.0},{"date":date2,"leverage":2.0}]
    point_times=[1251835260,1251921660]
    values={"close":[100,101],"sma50":[95,96],"sma200":[90,91],
            "vol20":[.2,.21],"mom12":[.1,.11],"level":[3,2],"defense":[0,0]}
    run={"charts":{
       CHART:{"series":{k:{"values":[[t,v] for t,v in zip(point_times,seq)]}
                        for k,seq in values.items()}},
       "SL724":{"series":{"Leverage":{"values":[[point_times[0],3],[point_times[1],2]]}}}
    }}
    p=tmp_path/"diagnostic.json";p.write_text(json.dumps(run))
    return p,original


def test_free_chart_acquisition_rejects_leverage_mismatch(tmp_path):
    p,orig=fixture(tmp_path)
    with patch("qc_chart_feature_acquisition.extract",return_value=(orig,{"source_sha256":"original"})):
        rows,audit=project("original.json",p)
        assert len(rows)==2
        assert rows[0]["defense"]=="false"
        assert audit["native_feature_serialization_exact_precision_proven"] is False
        assert audit["native_algorithm_source_identity_proven"] is False
        d=json.loads(p.read_text())
        d["charts"]["SL724"]["series"]["Leverage"]["values"][1][1]=3
        p.write_text(json.dumps(d))
        with pytest.raises(ValueError,match="CHANGED_FROZEN_LEVERAGE"):
            project("original.json",p)


def test_free_chart_acquisition_rejects_series_truncation(tmp_path):
    p,orig=fixture(tmp_path)
    d=json.loads(p.read_text())
    d["charts"][CHART]["series"]["mom12"]["values"].pop()
    p.write_text(json.dumps(d))
    with patch("qc_chart_feature_acquisition.extract",return_value=(orig,{"source_sha256":"original"})):
        with pytest.raises(ValueError,match="TRUNCATED_OR_WRONG_SESSION_COUNT"):
            project("original.json",p)


def test_free_chart_acquisition_rejects_wrong_day_alignment(tmp_path):
    p,orig=fixture(tmp_path)
    d=json.loads(p.read_text())
    d["charts"][CHART]["series"]["close"]["values"][1][0]+=86400
    p.write_text(json.dumps(d))
    with patch("qc_chart_feature_acquisition.extract",return_value=(orig,{"source_sha256":"original"})):
        with pytest.raises(ValueError,match="FEATURE_DATES_DO_NOT_MATCH"):
            project("original.json",p)

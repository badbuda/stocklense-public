"""Risk-matched frozen StockLens two-question audit regression and anti-lookahead."""
from __future__ import annotations

from copy import deepcopy
import math

import pytest

from observed_etf_two_question_audit import (
    _bootstrap_pair, _cap, _calibrate, _hac_alpha, _run, evaluate, load,
    SPLITS, VARIANTS, START_CAPITAL,
)


@pytest.fixture(scope="module")
def source():
    return load()


@pytest.fixture(scope="module")
def report(source):
    return evaluate(source, bootstrap_reps=40)


def test_reproduce_published_frozen_8_0_2010_to_2026_no_orders_invented(source, report):
    frozen=report["full_period_results"]["frozen"]
    published=source["without_contributions"]["strategy"]
    assert frozen["cagr"]==pytest.approx(published["cagr_without_contributions"],abs=.001)
    assert frozen["max_drawdown"]==pytest.approx(published["max_drawdown"],abs=.005)
    assert frozen["ending_equity"]==pytest.approx(published["ending_equity"],rel=.001)
    assert report["independent_vendor_fills_verified"] is False
    assert report["capital_deployment_authorized"] is False
    assert report["historically_pristine_holdout"] is False
    assert report["frozen_stocklens_8_mutated"] is False


def test_risk_matching_calibrated_only_in_historically_reused_development(source):
    rows=source["daily"]
    result=_calibrate(rows)
    mutated=deepcopy(rows)
    # A shock in an observed later period cannot alter 2010-17 training weights.
    mutated[-1]["tc"]*=.5
    assert _calibrate(mutated)==result
    assert all(0<=z["tqqq_weight"]<=.985 for z in result.values())
    assert SPLITS["development"][1]<SPLITS["validation_reused"][0]


def test_all_overlay_cap_features_use_only_the_prior_completed_close(source):
    closes=[row["qc"] for row in source["daily"]]
    i=700
    original={name:_cap(closes,i-1,name) for name in VARIANTS}
    tampered=closes.copy()
    tampered[i]*=.01
    tampered[i+1]*=50
    assert original=={name:_cap(tampered,i-1,name) for name in VARIANTS}
    assert all(z in (1.25,2,3) for z in original.values())


def test_critical_observed_price_missing_or_future_session_is_rejected(source,tmp_path):
    import json
    r=deepcopy(source)
    r["daily"][100]["to"]=0.
    p=tmp_path/"bad.json"
    p.write_text(json.dumps(r))
    with pytest.raises(ValueError,match="UNOBSERVED_OR_INVALID_ETF_PRICE"):
        load(p)
    r=deepcopy(source)
    r["daily"][100]["signal"]=r["daily"][100]["date"]
    p.write_text(json.dumps(r))
    with pytest.raises(ValueError,match="FUTURE_SIGNAL_OR_CONTRIBUTION"):
        load(p)


def test_overlay_never_increases_frozen_stocklens_exposure(source):
    rows=source["daily"][500:800]
    base=_run(rows,variant="frozen")
    for v in VARIANTS[1:]:
        result=_run(rows,variant=v)
        assert len(result["exposures"])==len(base["exposures"])
        assert all(a<=b for a,b in zip(result["exposures"],base["exposures"]))
        assert result["intervention_sessions"]>=0


def test_all_predeclared_splits_and_sensitivity_grid_are_reported(report):
    assert set(report["split_results"])==set(SPLITS)
    assert len(report["volatility_overlay_execution_cost_and_lag_stress"])==len(VARIANTS)*3*3
    assert {"volatility_matched_static","beta_matched_static","tqqq_static","qqq_static"} <= set(report["full_period_results"])
    for key,period in report["split_results"].items():
        assert "frozen" in period
        assert period["frozen"]["start"]>=SPLITS[key][0]
        assert period["frozen"]["end"]<=SPLITS[key][1]
    assert report["alpha_hac_vs_qqq_zero_cash_rate"]["full"]["not_clean_inference"] is True
    assert set(report["risk_matched_relative_log_bootstrap_NOT_P_VALUE"])=={"21","63"}


def test_hac_regression_identifies_known_linear_alpha_without_spurious_beta():
    x=[.01*math.sin(i*.17)+.007*math.cos(i*.05) for i in range(500)]
    y=[.001+2*z for z in x]
    out=_hac_alpha(y,x,lag=21)
    assert out["beta_to_qqq"]==pytest.approx(2,abs=1e-10)
    assert out["daily_arithmetic_alpha"]==pytest.approx(.001,abs=1e-10)


def test_bootstrap_identical_paths_never_creates_relative_growth():
    series=[START_CAPITAL*(1.00015)**i for i in range(150)]
    report=_bootstrap_pair(series,series,rep=20)
    for result in report.values():
        assert result["p50"]==0.
        assert result["positive_resample_fraction_NOT_P_VALUE"]==0.

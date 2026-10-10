"""Causal ML meta-exposure tests; fabricated OHLC only in test fixtures.

All investment claims on actual bars are computed separately in checked-in
historical data and clearly flagged repeated/reused, NOT independent holdout.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date,timedelta
import math

import numpy as np
import pytest

import observed_etf_causal_ml_meta_leverage as ml
from observed_etf_two_question_audit import _run as independent_frozen,load


def fake_rows(n=400):
    d=date(2020,1,2)
    o=[]
    while len(o)<n:
        if d.weekday()<5:
            i=len(o)
            q=100*math.exp(.00025*i+.018*math.sin(i/11.))
            t=40*math.exp(.0004*i+.052*math.sin(i/11.))
            lev=(0 if i%113==0 else 1.25 if i%23<4 else
                 2 if i%23<10 else 3)
            o.append({"date":d.isoformat(),"signal":(d-timedelta(days=1)).isoformat(),
               "qo":q*math.exp(.001*math.sin(i)),"qc":q,
               "to":t*math.exp(.003*math.sin(i)),"tc":t,
               "l":lev,"contribution":0})
        d+=timedelta(days=1)
    return o


def small_wf(rows):
    return ml.walkforward(rows,start=rows[315]["date"],
                          train_min=30,train_window=80)


def test_all_signals_use_last_completed_close_not_open_or_same_day_close():
    a=fake_rows()
    i=319
    x=ml.feature_at(a,i)
    b=deepcopy(a)
    b[i]["qo"]*=.33
    b[i]["qc"]*=.41
    b[i]["to"]*=1.35
    b[i]["tc"]*=1.48
    y=ml.feature_at(b,i)
    np.testing.assert_array_equal(x,y)
    assert ml.forward_label(a,i)!=ml.forward_label(b,i)


def test_training_label_fully_matured_plus_5day_embargo_before_any_monthly_fit():
    rows=fake_rows()
    wf=small_wf(rows)
    dates=[r["date"] for r in rows]
    assert len(wf["fits"])>=2
    assert wf["first_test_index"]==315
    assert all(wf["predictions"][i] is None for i in range(315))
    for f in wf["fits"]:
        fit_i=dates.index(f["fit_date"])
        latest_index=dates.index(f["last_completed_training_label_date"])
        assert latest_index <=fit_i-ml.EMBARGO-1
        assert f["training_count"]>=30
        assert dates.index(f["last_training_signal"])+ml.HORIZON-1==latest_index


def test_unknown_future_prices_cannot_rewrite_predictions_from_past():
    a=fake_rows()
    first=small_wf(a)
    b=deepcopy(a)
    shock=374
    b[shock]["qc"]*=.65
    b[shock]["tc"]*=.5
    changed=small_wf(b)
    assert first["predictions"][:shock+1]==pytest.approx(
        changed["predictions"][:shock+1])
    assert first["fits"][:2]==changed["fits"][:2]


def test_monthly_fit_is_repeatable_without_random_seed():
    a=fake_rows()
    p=small_wf(a)
    q=small_wf(a)
    assert p["fits"]==q["fits"]
    assert p["predictions"][315:]==q["predictions"][315:]


@pytest.mark.parametrize("mode",ml.MODES)
def test_no_challenger_can_override_frozen_cash_or_reach_above_3x(mode):
    for frozen in (0.,1.25,2.,3.):
        for prediction in (-.15,0.,.15):
            f=np.array([.0,.10,.0,.18,.2,.05,-.01,.1,.001])
            outcome=ml.candidate_level(frozen,prediction,f,mode)
            assert outcome in (0.,1.25,2.,3.)
            assert outcome<=3.
            if frozen==0.:
                assert outcome==0.


def test_one_step_up_and_down_exact_prepublished_rules():
    f=np.array([.0,.10,.0,.18,.2,.05,-.01,.1,.001])
    assert ml.candidate_level(1.25,.01,f,"ml_ups")==2.
    assert ml.candidate_level(2.,.01,f,"ml_ups")==3.
    assert ml.candidate_level(3.,.01,f,"ml_ups")==3.
    assert ml.candidate_level(3.,-.01,f,"ml_down")==2.
    assert ml.candidate_level(2.,-.01,f,"ml_down")==1.25
    assert ml.candidate_level(1.25,-.01,f,"ml_down")==1.25
    assert ml.candidate_level(3.,-.01,f,"ml_both")==2.
    assert ml.candidate_level(3.,.01,f,"ml_both")==3.
    assert ml.candidate_level(1.25,None,f,"ml_both")==1.25


def test_fake_full_frozen_nav_replays_independent_engine_daily():
    rows=fake_rows()
    wf=small_wf(rows)
    actual=ml.simulate(rows,wf)
    ref=independent_frozen(rows,variant="frozen")
    assert len(actual["navs"])==len(ref["navs"])
    np.testing.assert_allclose(actual["navs"],ref["navs"],rtol=1e-11,atol=1e-5)
    assert actual["trades"]==ref["trades"]


def test_extra_ml_signal_delay_does_not_use_current_model_score():
    rows=fake_rows()
    wf=small_wf(rows)
    p=ml.simulate(rows,wf,mode="ml_both",lag=1)
    f=ml.simulate(rows,wf,mode="frozen",lag=0)
    assert p["levels"][:316]==f["levels"][:316]
    for got,original in zip(p["levels"],[r["l"] for r in rows]):
        assert original==0 or got<=3.


def test_training_cannot_start_while_target_label_future_is_unseen():
    rows=fake_rows()
    with pytest.raises(ValueError,match="NOT_ENOUGH_PRIOR_TRAINING"):
        ml.walkforward(rows,start=rows[266]["date"],train_min=30,train_window=80)
    with pytest.raises(ValueError,match="UNREGISTERED_HORIZON_OR_EMBARGO"):
        ml.walkforward(rows,start=rows[315]["date"],train_min=30,
                       train_window=80,horizon=2)


def test_duplicate_dates_future_frozen_signal_and_mutated_state_fail_closed():
    rows=fake_rows()
    rows[330]["date"]=rows[329]["date"]
    with pytest.raises(ValueError,match="FUTURE_OR_DUPLICATE_OBSERVED_SESSIONS"):
        small_wf(rows)
    rows=fake_rows()
    rows[329]["signal"]=rows[329]["date"]
    with pytest.raises(ValueError,match="LOOKAHEAD_OR_MUTATED_FROZEN_LEVEL"):
        small_wf(rows)
    rows=fake_rows()
    rows[329]["l"]=5.
    with pytest.raises(ValueError,match="LOOKAHEAD_OR_MUTATED_FROZEN_LEVEL"):
        small_wf(rows)


def test_reject_nan_predictions_and_posthoc_challenger_names():
    with pytest.raises(ValueError,match="NONFINITE_ML_PREDICTION"):
        ml.candidate_level(2.,float("nan"),None,"ml_ups")
    with pytest.raises(ValueError,match="UNREGISTERED_ML_CHALLENGER"):
        ml.candidate_level(2.,.5,None,"made_up_variant")


def test_performance_stress_never_implies_real_execution():
    rows=fake_rows()
    wf=small_wf(rows)
    r=ml.simulate(rows,wf,mode="ml_ups",lag=1,slip=20.)
    assert r["real_broker_fills_observed"] is False
    assert r["stats"]["ending_equity"]>0
    assert r["trades"]>=1
    assert r["upshift_sessions"]>=0
    with pytest.raises(ValueError,match="UNREGISTERED_MODE_LAG_OR_COST"):
        ml.simulate(rows,wf,mode="ml_both",lag=3)


def test_real_observed_data_source_is_yahoo_not_lean_or_synthetic():
    raw=load()
    assert raw["observed_ohlc_available"] is True
    assert raw["full_lean_broker_parity"] is False
    assert raw["live_trading_authorized"] is False
    assert ml.FIRST_TEST=="2018-01-02"
    assert ml.TRAIN_SESSIONS==756
    assert ml.EMBARGO==5
    assert ml.HORIZON==5
    assert ml.SLIPPAGE_BPS==(10.,20.,30.)
    assert ml.RANDOMNESS.startswith("NONE")

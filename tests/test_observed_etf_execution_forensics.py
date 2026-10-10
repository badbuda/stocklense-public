"""Adversarial accounting tests: all market-data fabrications confined to fixtures."""
from __future__ import annotations

from copy import deepcopy
from datetime import date, timedelta
import math

import pytest

from observed_etf_execution_forensics import replay, distinct_drawdowns, tails, evaluate
from observed_etf_two_question_audit import load, _run


@pytest.fixture(scope="module")
def observed():
    return load()["daily"]


def short_history(n=160):
    today=date(2025,1,2)
    rows=[]
    while len(rows)<n:
        if today.weekday()<5:
            i=len(rows)
            q=100.*(1.0001**i)
            t=40.*(1.0003**i)
            rows.append({"date":today.isoformat(),
                         "signal":(today-timedelta(days=1)).isoformat(),
                         "l":3 if i<45 or i>=88 else 1.25,
                         "qo":q,"qc":q*1.001,
                         "to":t,"tc":t*1.002})
        today+=timedelta(days=1)
    return rows


@pytest.mark.parametrize("lag", (0,1,2))
def test_reconciliation_day_by_day_has_precisely_three_parts(lag):
    records=replay(short_history(),delay=lag)["rows"]
    assert len(records)==160
    for r in records:
        c=r["log_components"]
        assert sum(c.values())==pytest.approx(math.log1p(r["daily_return"]),abs=1e-11)
        assert r["prior_nav"]+r["overnight_dollar_pnl"]+r["intraday_dollar_pnl"]-r["model_fees"]-r["model_slippage"]==pytest.approx(r["nav"],abs=.0001)


def test_replay_same_daily_nav_as_original_independent_engine(observed):
    source=observed[:800]
    a=replay(source)
    b=_run(source,variant="frozen")
    assert len(a["rows"])==len(b["navs"])
    for x,y in zip(a["rows"],b["navs"]):
        assert x["nav"]==pytest.approx(y,rel=1e-11,abs=.0001)
    assert a["metrics"]["max_drawdown"]==pytest.approx(b["stats"]["max_drawdown"],abs=1e-10)


def test_closed_day_future_price_perturb_cannot_change_past_decisions():
    a=short_history()
    b=deepcopy(a)
    i=95
    b[i]["qc"]*=.75
    b[i]["tc"]*=.67
    x=replay(a)["rows"]
    y=replay(b)["rows"]
    for j in range(i):
        assert x[j]==y[j]
    assert x[i]["rebalance"]==y[i]["rebalance"]
    assert x[i]["signal"]==y[i]["signal"]
    assert x[i]["overnight_dollar_pnl"]==y[i]["overnight_dollar_pnl"]


def test_rebalance_gap_liquidity_penalty_uses_observed_open_not_fake_price():
    r=short_history(100)
    i=45
    r[i]["qo"]=r[i-1]["qc"]*.92
    r[i]["to"]=r[i-1]["tc"]*.80
    base=replay(r,extra_gap_slip=0.)
    costly=replay(r,extra_gap_slip=60.)
    assert costly["penalized_rebalance_sessions"]>=1
    assert costly["rows"][i]["gap_liquidity_penalty_bps"]==60.
    assert base["rows"][i]["gap_liquidity_penalty_bps"]==0.
    assert costly["rows"][i]["model_slippage"]>base["rows"][i]["model_slippage"]
    assert costly["rows"][i]["nav"] < base["rows"][i]["nav"]
    assert r[i]["qo"]==pytest.approx(r[i-1]["qc"]*.92)  # underlying price never mutated


def test_gap_penalty_without_order_is_not_fabricated_execution_cost():
    r=short_history()
    i=65  # no target change around this date
    r[i]["qo"]=r[i-1]["qc"]*.90
    r[i]["to"]=r[i-1]["tc"]*.85
    got=replay(r,extra_gap_slip=60.)["rows"][i]
    assert got["model_orders"]==0
    assert got["gap_liquidity_penalty_bps"]==0.
    assert got["overnight_dollar_pnl"]<0.


@pytest.mark.parametrize("mutation,code",[
    (lambda r:r[8].update(qo=0.),"BAD_OBSERVED_PRICE"),
    (lambda r:r[8].update(to=float("nan")),"BAD_OBSERVED_PRICE"),
    (lambda r:r[8].update(signal=r[8]["date"]),"BAD_DATE_OR_FUTURE_SIGNAL"),
    (lambda r:r[8].update(l=9),"INVALID_FROZEN_EXPOSURE"),
    (lambda r:r[8].update(date=r[7]["date"]),"BAD_DATE_OR_FUTURE_SIGNAL"),
])
def test_replay_rejects_corrupted_prices_or_lookahead(mutation,code):
    r=short_history()
    mutation(r)
    with pytest.raises(ValueError,match=code):
        replay(r)


def test_replay_rejects_posthoc_tuned_stress_parameters():
    r=short_history()
    with pytest.raises(ValueError,match="UNREGISTERED_STRESS_VARIANT"):
        replay(r,delay=4)
    with pytest.raises(ValueError,match="UNREGISTERED_STRESS_VARIANT"):
        replay(r,extra_gap_slip=999.)


def test_distinct_drawdown_recovery_censoring_and_log_conservation():
    p=[110000.,80000.,90000.,115000.,100000.,95000.]
    rows=[]
    prev=100000.
    for i,nav in enumerate(p):
        c=math.log(nav/prev)
        rows.append({"date":f"2025-01-{i+2:02d}","nav":nav,
                     "prior_frozen_level":3.,"daily_return":nav/prev-1.,
                     "log_components":{"overnight":c*.25,"intraday":c*.75,"execution":0.}})
        prev=nav
    e=distinct_drawdowns(rows)
    assert len(e)==2
    deepest=e[0]
    assert deepest["peak_date"]=="2025-01-02"
    assert deepest["trough_date"]=="2025-01-03"
    assert deepest["recovery_date"]=="2025-01-05"
    assert deepest["recovery_right_censored"] is False
    assert e[1]["recovery_right_censored"] is True
    assert e[1]["recovery_date"] is None


def test_overlay_does_not_get_a_different_episode_peak_when_comparing():
    r=short_history(100)
    x=replay(r)
    epi=distinct_drawdowns(x["rows"])
    for event in epi:
        assert event["trough_date"]>=event["peak_date"] if event["peak_date"]!="INCEPTION" else True


def test_empirical_risk_includes_rolling_underwater_and_daily_gap():
    r=short_history(280)
    risk=tails(replay(r)["rows"])
    assert set(risk["worst_rolling_simple_returns"])=={"21","63","252"}
    assert risk["empirical_daily_ES_1pct"]<=risk["empirical_daily_ES_5pct"]

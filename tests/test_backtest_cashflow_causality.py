import math
from backtest_contract import FrozenExposureReplayAdapter, stocklens_8_request
from backtest_engine import run_backtest

def rows():
    return [
        {"date":"2026-01-30","close":100.,"leverage":1.,"event":False},
        {"date":"2026-02-02","close":110.,"leverage":1.,"event":False},
        {"date":"2026-02-03","close":110.,"leverage":1.,"event":False},
        {"date":"2026-03-02","close":99.,"leverage":1.,"event":False},
    ]

def run(monthly):
    return run_backtest(rows(),stocklens_8_request(initial=100.,monthly=monthly,cost_bps=0.),FrozenExposureReplayAdapter())

def test_contributions_excluded_from_time_weighted_daily_returns():
    x=run(50.)
    daily=[z["twr_daily_return"] for z in x["ledger"][1:]]
    assert all(math.isclose(a,b,abs_tol=1e-12) for a,b in zip(daily,(.10,0.,-.10)))
    assert math.isclose(x["analytics"]["time_weighted_return"],-.01,abs_tol=1e-12)
    assert math.isclose(x["analytics"]["time_weighted_growth_index"],.99,abs_tol=1e-12)
    assert x["analytics"]["cagr_without_contribution_distortion"] is None

def test_contribution_rising_nav_must_not_hide_strategy_drawdown():
    x=run(50.)
    assert x["end_equity"]>x["ledger"][0]["net_nav"]
    assert math.isclose(x["max_drawdown"],-.1,abs_tol=1e-12)
    assert math.isclose(x["analytics"]["legacy_cashflow_distorted_nav_drawdown"],0.,abs_tol=1e-12)
    assert x["ledger"][-1]["drawdown"]<0

def test_zero_contributions_still_has_same_strategy_return():
    x=run(0.)
    assert math.isclose(x["max_drawdown"],-.1,abs_tol=1e-12)
    assert math.isclose(x["analytics"]["time_weighted_return"],-.01,abs_tol=1e-12)

def test_frozen_adapter_causality_uses_previous_session_only():
    a=FrozenExposureReplayAdapter()
    previous={"date":"2026-03-01","close":100.,"leverage":3.}
    current={"date":"2026-03-02","close":110.,"leverage":1.}
    baseline=a.target_exposure(previous,current)
    for key,value in (("close",1.0),("close",1e9),("leverage",0.0),("leverage",3.0)):
        assert a.target_exposure(previous,{**current,key:value})==baseline==3.0

def test_generic_replay_current_price_changes_return_not_prior_exposure():
    original=rows()
    changed=[dict(x) for x in original]
    changed[1]["close"]=220.
    request=stocklens_8_request(initial=100.,monthly=0.,cost_bps=0.)
    b=FrozenExposureReplayAdapter()
    x=run_backtest(original,request,b)
    y=run_backtest(changed,request,b)
    assert x["ledger"][1]["exposure"]==y["ledger"][1]["exposure"]==1.
    assert x["ledger"][1]["twr_daily_return"]!=y["ledger"][1]["twr_daily_return"]

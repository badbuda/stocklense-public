"""Causal fixture checks for prior-session Vol60 + risk-cap ramp/re-entry.

Any fabricated OHLC here exists ONLY in test fixtures. Published performance
always reads checked-in historical Yahoo QQQ/TQQQ adjusted ETF observations.
"""
from __future__ import annotations

from datetime import date, timedelta
from copy import deepcopy
import math

import pytest

import observed_etf_vol60_reentry_audit as mod
from observed_etf_two_question_audit import load, _run as reference_frozen


@pytest.fixture(scope="module")
def observed_rows():
    return load()["daily"]


def test_frozen_daily_nav_identical_to_existing_validated_trade_engine(observed_rows):
    source=observed_rows[:350]
    independent=mod.simulate(source,mode="frozen")
    original=reference_frozen(source,variant="frozen")
    assert len(independent["navs"])==len(original["navs"])
    for a,b in zip(independent["navs"],original["navs"]):
        assert a==pytest.approx(b,abs=1e-5,rel=1e-10)
    assert independent["stats"]["max_drawdown"]==pytest.approx(
        original["stats"]["max_drawdown"],abs=1e-12)


@pytest.mark.parametrize("mode",mod.MODES)
def test_real_tqqq_observed_open_research_never_increases_frozen_exposure(
        observed_rows,mode):
    sample=observed_rows[500:900]
    result=mod.simulate(sample,mode=mode)
    assert len(result["levels"])==len(sample)
    assert result["actual_broker_fills_observed"] is False
    assert all(0<=got<=float(r["l"])+1e-10
               for got,r in zip(result["levels"],sample))
    assert result["stats"]["ending_equity"]>0


def test_future_qqq_close_perturbation_cannot_change_previous_orders_or_levels(
        observed_rows):
    rows=deepcopy(observed_rows[750:1000])
    original=mod.simulate(rows,mode="vol60_ramp5")
    future_day=200
    rows[future_day]["qc"]*=.81
    adjusted=mod.simulate(rows,mode="vol60_ramp5")
    # The changed close at t may alter its mark, not its pre-open decision.
    assert adjusted["levels"][:future_day+1]==pytest.approx(
        original["levels"][:future_day+1])
    assert adjusted["navs"][:future_day]==pytest.approx(
        original["navs"][:future_day])


def test_reentry_raised_by_at_most_fixed_ramp_from_cap_not_future_prices(
        monkeypatch):
    def fixtures(n=45):
        out=[]
        d=date(2025,1,2)
        while len(out)<n:
            if d.weekday()<5:
                prior=(d-timedelta(days=1)).isoformat()
                out.append({"date":d.isoformat(),"signal":prior,"l":3,
                            "qo":100.,"qc":100.,"to":40.,"tc":40.})
            d+=timedelta(days=1)
        return out
    rows=fixtures()
    rv=[.1]*len(rows)
    rv[24]=.60   # cap 1x on next observed session, fast downside exit
    rv[25]=.10   # raw cap instantly restores 3x but ramp must be gradual
    monkeypatch.setattr(mod,"_features",lambda observed:(rv,[False]*len(observed)))
    immediate=mod.simulate(rows,mode="vol60_instant")["levels"]
    ramp5=mod.simulate(rows,mode="vol60_ramp5")["levels"]
    ramp10=mod.simulate(rows,mode="vol60_ramp10")["levels"]
    hold5=mod.simulate(rows,mode="vol60_hold5_ramp5")["levels"]
    assert immediate[25]==pytest.approx(1.)
    assert ramp5[25]==pytest.approx(1.)
    assert ramp10[25]==pytest.approx(1.)
    assert ramp5[26]==pytest.approx(1.4)
    assert ramp10[26]==pytest.approx(1.2)
    assert immediate[26]==pytest.approx(3.)
    assert hold5[26:30]==[1.]*4
    assert hold5[30]==pytest.approx(1.4)
    assert all(x<=3 and x>=1 for x in hold5)


def test_closed_market_or_wrong_price_is_not_silently_filled(observed_rows):
    rows=deepcopy(observed_rows[:100])
    rows[50]["to"]=0.
    with pytest.raises(ValueError,match="INVALID_OBSERVED_OPEN_OR_CLOSE"):
        mod.simulate(rows,mode="frozen")


def test_future_frozen_signal_or_invalid_hypothesis_is_fail_closed(observed_rows):
    rows=deepcopy(observed_rows[:100])
    rows[5]["signal"]=rows[5]["date"]
    with pytest.raises(ValueError,match="LOOKAHEAD_IN_FROZEN_SIGNAL"):
        mod.simulate(rows)
    with pytest.raises(ValueError,match="UNREGISTERED_HYPOTHESIS_OR_STRESS"):
        mod.simulate(observed_rows[:30],mode="retuned_after_outcome")
    with pytest.raises(ValueError,match="UNREGISTERED_HYPOTHESIS_OR_STRESS"):
        mod.simulate(observed_rows[:30],mode="vol60_instant",lag=3)


def test_only_predeclared_cap_modes_are_eligible_and_cannot_promote():
    assert set(mod.PREDECLARED)==set(mod.MODES)
    for name,(ramp,hold,shock) in mod.PREDECLARED.items():
        assert ramp in (0,5,10)
        assert hold in (0,5,10)
        assert isinstance(shock,bool)
    assert mod.SLIPPAGE_BPS==(10.,20.,30.)
    assert mod.LAGS==(0,1,2)


def test_repeated_simulation_is_deterministic_on_matched_observed_prices(
        observed_rows):
    subset=observed_rows[500:660]
    a=mod.simulate(subset,mode="vol60_hold5_ramp5",lag=1,slippage_bps=20.)
    b=mod.simulate(subset,mode="vol60_hold5_ramp5",lag=1,slippage_bps=20.)
    assert a==b


def test_report_conclusions_never_call_green_ci_live_ready():
    source=mod.human_report({
        "period":{"start":"2010-02-11","end":"2026-10-09"},
        "full_period_results":{n:{
            "cagr":.4,"max_drawdown":-.49,"cagr_delta_pp":0,
            "maxdd_improvement_pp":0,"intervention_sessions":0,
            "trades":0} for n in mod.MODES},
        "split_results_no_portfolio_restart":{
            n:{m:{"cagr_delta_pp":0,"maxdd_improvement_pp":0}
               for m in mod.MODES}
            for n in mod.SPLITS},
        "robustness_gate":{n:{"passed_stress_scenarios":0,
            "historical_continue_gate":False} for n in mod.MODES[1:]},
    })
    assert "broker fills" in source
    assert "no automatic challenger promotion" in source
    assert "not pristine OOS" in source

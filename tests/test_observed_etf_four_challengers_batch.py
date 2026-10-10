"""No-lookahead, unchanged frozen ledger, locked multiplicity and cash checks."""
from copy import deepcopy
from datetime import date, timedelta
import pytest

import observed_etf_four_challengers_batch as c
from observed_etf_two_question_audit import _run as prior_baseline, load


def fixture_rows(n=85):
    out=[]
    day=date(2023,1,2)
    while len(out)<n:
        if day.weekday()<5:
            t=len(out)
            level = 2 if t<27 else 3 if t<45 else 1.25 if t<65 else 0.
            out.append({"date":day.isoformat(),
                "signal":(day-timedelta(days=1)).isoformat(),"l":level,
                "qo":100.,"qc":100.+.05*t,"to":30.,"tc":30.+.035*t})
        day+=timedelta(days=1)
    return out


def test_frozen_matches_existing_daily_engine_exactly():
    rows=load()["daily"][:250]
    new=c.simulate(rows,mode="frozen")
    old=prior_baseline(rows,variant="frozen",lag=0,fee_bps=2.,slip_bps=10.)
    assert len(new["navs"])==len(old["navs"])
    assert new["navs"]==pytest.approx(old["navs"],rel=1e-11,abs=1e-5)


@pytest.mark.parametrize("mode",c.MODES)
def test_only_valid_modelled_etf_weights_and_frozen_defense(mode):
    rows=fixture_rows()
    result=c.simulate(rows,mode=mode)
    assert len(result["levels"])==len(rows)
    assert result["levels"][-1]==0.
    assert all(0<=x<=3 for x in result["levels"])
    assert result["stats"]["ending_equity"]>0


def test_entry_stage_and_exit_variants():
    rows=fixture_rows()
    up=c.simulate(rows,mode="staged_up_3")["levels"]
    both=c.simulate(rows,mode="staged_both_3")["levels"]
    assert up[27:30]==pytest.approx([2+1/3,2+2/3,3])
    assert both[27:30]==pytest.approx([2+1/3,2+2/3,3])
    assert up[45]==1.25
    assert both[45]==pytest.approx(3+(1.25-3)/3)
    assert all(v==0 for v in up[65:])


def test_ewma_open_decisions_do_not_see_same_day_close():
    rows=fixture_rows()
    a=c.simulate(rows,mode="ewma5_shock")["levels"]
    mutated=deepcopy(rows)
    mutated[48]["qc"]*=.6
    b=c.simulate(mutated,mode="ewma5_shock")["levels"]
    assert a[:49]==pytest.approx(b[:49])


def test_cash_yield_is_explicit_scenario_and_not_assumed_real():
    rows=fixture_rows()
    rows=[{**r,"l":0.} for r in rows]
    x=c.simulate(rows,annual_cash_yield=0.)
    y=c.simulate(rows,annual_cash_yield=.04)
    assert y["stats"]["ending_equity"]>x["stats"]["ending_equity"]
    assert y["cash_interest"]>0
    with pytest.raises(ValueError,match="UNDECLARED_CASH_RATE"):
        c.simulate(rows,annual_cash_yield=.055)


def test_fail_closed_on_invalid_history_or_unregistered_variants():
    rows=fixture_rows()
    with pytest.raises(ValueError,match="UNDECLARED_MODE"):
        c.simulate(rows,mode="optimized_after_results")
    broken=deepcopy(rows)
    broken[15]["signal"]=broken[15]["date"]
    with pytest.raises(ValueError,match="LOOKAHEAD"):
        c.simulate(broken)
    broken=deepcopy(rows)
    broken[15]["to"]=-1.
    with pytest.raises(ValueError,match="NOT_REAL"):
        c.simulate(broken)


def test_experiment_families_are_fixed_and_not_promoted():
    assert len(c.CHALLENGERS)==5
    assert c.LAGS==(0,1)
    assert c.SLIPPAGES_BPS==(10.,20.)
    assert c.CASH_RATE_SCENARIOS==(0.,.02,.04)

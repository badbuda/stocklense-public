"""Toy prices only test as-of behavior. They are not new investment results."""
import copy
import math
import pytest
from observed_etf_inverse_variance_drag_study import (
    finished_features,cap,simulate,TARGET_ANNUAL_QQQ_VOL
)
from observed_etf_four_challengers_batch import simulate as frozen_reference


def mock_rows():
    d=[f"2024-02-{1+i:02d}" for i in range(26)]
    # Stub dates only for synthetic unit test; not XNYS market-performance evidence.
    return [{"date":date,"signal":"2024-01-31" if i==0 else d[i-1],
             "l":3,"qo":100.+i,"qc":100.+i*(1 if i%2 else -1)*.8,
             "to":25.+i*.1,"tc":25.+i*.1} for i,date in enumerate(d)]


def test_inverse_variance_and_downside_caps_differ_and_never_raise_leverage():
    for sigma in (.2,.4,.8):
        x=cap("inverse_variance20",sigma,sigma)
        y=cap("downside_semivariance20",sigma,sigma)
        assert 1 <= x <= 3 and 1 <= y <= 3
    assert cap("inverse_variance20",.4,.4)==pytest.approx(2.25)
    assert cap("downside_semivariance20",.4,.4)==pytest.approx(1.5)
    assert cap("frozen",.4,.4)==3


def test_no_same_session_close_in_daily_preopen_volatility_feature():
    rows=mock_rows()
    base=simulate(rows,mode="inverse_variance20")
    newer=copy.deepcopy(rows)
    newer[-1]["qc"]*=1.5
    after=simulate(newer,mode="inverse_variance20")
    assert base["navs"][:-1]==after["navs"][:-1]


def test_frozen_ledger_parity_small_toy_prices():
    rows=mock_rows()
    for slip in (10.,20.):
        a=simulate(rows,mode="frozen",slip=slip)["navs"]
        b=frozen_reference(rows,mode="frozen",lag=0,slippage_bps=slip)["navs"]
        assert a==pytest.approx(b,abs=1e-6)


def test_bad_sigma_and_invalid_unregistered_rules_fail_closed():
    with pytest.raises(ValueError,match="DRAG_INVALID_SIGMA"):
        cap("inverse_variance20",math.nan,1.)
    with pytest.raises(ValueError,match="DRAG_UNREGISTERED"):
        cap("best_posthoc",.4,.4)
    with pytest.raises(ValueError,match="DRAG_UNREGISTERED"):
        simulate(mock_rows(),mode="best_posthoc")


def test_corrupted_daily_bars_and_future_signals_rejected():
    r=mock_rows();r[2]["to"]=float("nan")
    with pytest.raises(ValueError,match="DRAG_INVALID_OBSERVED"):
        simulate(r)
    r=mock_rows();r[2]["signal"]=r[2]["date"]
    with pytest.raises(ValueError,match="DRAG_FUTURE"):
        simulate(r)

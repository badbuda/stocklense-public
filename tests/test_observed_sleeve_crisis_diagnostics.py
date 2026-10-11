"""Unit stress diagnostics with synthetic TEST inputs only; no alpha claims."""
import pytest
from observed_sleeve_crisis_diagnostics import _case_series, _peak_to_trough, _worst_daily


def fake():
    return {"dates":["2024-01-02","2024-01-03","2024-01-04","2024-01-05"],
            "navs":[100.,110.,88.,93.5]}


def test_crisis_window_endpoint_distinct_from_maxdd():
    x=_case_series(fake(),"2024-01-02","2024-01-05")
    assert x["endpoint_close_to_close_return"] == pytest.approx(-.065)
    assert x["local_window_max_drawdown"] == pytest.approx(-.20)
    assert x["local_peak_session"]=="2024-01-03"
    assert x["local_trough_session"]=="2024-01-04"


def test_window_not_in_observed_source_raises():
    with pytest.raises(ValueError,match="DIAGNOSTICS_PREDECLARED_WINDOW_UNOBSERVED"):
        _case_series(fake(),"2025-01-01","2025-02-01")


def test_worst_daily_is_based_on_consecutive_navs():
    x=_worst_daily(fake())
    assert x["return"]==pytest.approx(-.2)
    assert x["session"]=="2024-01-04"


def test_peak_to_trough_initial_open_not_imaginary_price():
    dd,h,l=_peak_to_trough(fake()["navs"])
    assert dd==pytest.approx(-.2)
    assert (h,l)==(1,2)

from datetime import date, timedelta

import pytest

from tradable_tqqq_execution_comparison import _validate_prices, run_execution


def _fixture():
    qqq = {}
    tqqq = {}
    start = date(2008, 1, 2)
    day = start
    ix = 0
    while len(qqq) < 4300:
        if day.weekday() < 5:
            q_price = 50 * (1.00014 ** ix)
            t_price = 5 * (1.00031 ** ix)
            label = day.isoformat()
            qqq[label] = {"open": q_price, "close": q_price * 1.001}
            if label >= "2010-02-09":
                tqqq[label] = {"open": t_price, "close": t_price * 1.003}
            ix += 1
        day += timedelta(days=1)
    signals = {key: 3.0 for key in qqq}
    return qqq, tqqq, signals


@pytest.fixture(scope="module")
def synthetic_market():
    return _fixture()


def test_observed_tqqq_not_three_times_qqq(synthetic_market):
    q, t, decisions = synthetic_market
    result = run_execution(q, t, decisions)
    assert result["start"] >= "2010-02-09"
    assert result["sessions"] > 3000
    assert result["stocklens"]["trades"] >= 1
    assert result["qqq_buy_hold"]["trades"] >= 1
    assert result["stocklens"]["ending_shares"]["TQQQ"] > 0
    assert result["stocklens"]["ending_shares"]["QQQ"] == 0
    assert result["stocklens"]["cagr_without_contributions"] is not None
    assert result["stocklens"]["total_modeled_commissions"] > 0
    assert result["stocklens"]["total_modeled_slippage"] > 0


def test_latest_close_never_traded_in_same_session(synthetic_market):
    q, t, signals = synthetic_market
    before = run_execution(q, t, signals)
    changed = dict(signals)
    changed[max(q)] = 0.0
    after = run_execution(q, t, changed)
    assert before["stocklens"] == after["stocklens"]
    assert before["qqq_buy_hold"] == after["qqq_buy_hold"]


def test_defensive_cash_and_costs(synthetic_market):
    q, t, _ = synthetic_market
    result = run_execution(q, t, {d: 0.0 for d in q})
    assert result["stocklens"]["ending_equity"] == pytest.approx(100_000)
    assert result["stocklens"]["trades"] == 0
    assert result["stocklens"]["max_drawdown"] == 0
    assert result["qqq_buy_hold"]["trades"] > 0


def test_extra_signal_lag_changes_trade_date_not_price_date(synthetic_market):
    q, t, signals = synthetic_market
    change_date = next(d for d in q if d >= "2021-06-01")
    amended = {d: 0.0 if d < change_date else 3.0 for d in q}
    base = run_execution(q, t, amended, extra_signal_lag=0)
    lagged = run_execution(q, t, amended, extra_signal_lag=2)
    new_base = next(x["date"] for x in base["events"] if x["target_leverage"] == 3.0)
    new_lagged = next(x["date"] for x in lagged["events"] if x["target_leverage"] == 3.0)
    assert new_base < new_lagged


def test_contributions_and_no_short(synthetic_market):
    q, t, signals = synthetic_market
    result = run_execution(q, t, signals, monthly=3500)
    assert result["stocklens"]["paid_capital"] > 100_000
    assert result["qqq_buy_hold"]["paid_capital"] == result["stocklens"]["paid_capital"]
    assert result["stocklens"]["ending_cash"] >= 0
    assert result["stocklens"]["ending_shares"]["TQQQ"] >= 0
    assert result["stocklens"]["cagr_without_contributions"] is None


def test_missing_observed_tqqq_session_fails_closed(synthetic_market):
    q, t, signals = synthetic_market
    damaged = dict(t)
    damaged.pop(list(damaged)[1])
    with pytest.raises(ValueError, match="MISSING_TQQQ_TRADING_SESSIONS"):
        run_execution(q, damaged, signals)


def test_non_frozen_exposure_rejected(synthetic_market):
    q, t, signals = synthetic_market
    rogue = dict(signals)
    rogue[next(d for d in q if d >= "2010-02-08")] = 2.5
    with pytest.raises(ValueError, match="FROZEN_EXPOSURE_NOT_RECOGNIZED"):
        run_execution(q, t, rogue)


def test_cashflow_adjusted_drawdown_is_explicit_and_finite(synthetic_market):
    q, t, signals = synthetic_market
    base = run_execution(q, t, signals)
    funded = run_execution(q, t, signals, monthly=3500)
    for side in ("stocklens", "qqq_buy_hold"):
        a = base[side]
        b = funded[side]
        assert a["max_drawdown_method"] == "RAW_NAV_NO_EXTERNAL_CONTRIBUTIONS"
        assert a["max_drawdown"] == pytest.approx(a["raw_equity_max_drawdown"])
        assert a["max_drawdown"] == pytest.approx(a["cashflow_adjusted_max_drawdown"])
        assert b["max_drawdown_method"] == "CHAINED_NAV_EXCLUDING_START_OF_SESSION_EXTERNAL_CASHFLOWS"
        assert b["max_drawdown"] == pytest.approx(b["cashflow_adjusted_max_drawdown"])
        assert -1.0 <= b["max_drawdown"] <= 0.0
        assert b["paid_capital"] > a["paid_capital"]


def test_cash_only_monthly_contributions_are_not_reported_as_market_returns(synthetic_market):
    q, t, _ = synthetic_market
    out = run_execution(q, t, {day: 0.0 for day in q}, monthly=3500)
    cash = out["stocklens"]
    assert cash["max_drawdown"] == 0.0
    assert cash["cashflow_adjusted_max_drawdown"] == 0.0
    assert cash["profit_loss"] == pytest.approx(0.0)
    assert cash["cagr_without_contributions"] is None


def test_rolling_risk_windows_derived_from_actual_portfolio_nav(synthetic_market):
    q, t, decisions = synthetic_market
    data = run_execution(q, t, decisions, monthly=0)
    windows = data["rolling_observed_etf_windows"]
    assert set(windows) == {"21", "63", "252", "756", "1260"}
    assert windows["1260"]["window_count"] > 0
    for sample in windows.values():
        assert 0 <= sample["stocklens_above_qqq"] <= sample["window_count"]
        assert sample["worst_stocklens_window_return"] > -1
    with_contributions = run_execution(q, t, decisions, monthly=3500)
    assert with_contributions["rolling_observed_etf_windows"] is None

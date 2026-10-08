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

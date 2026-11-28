from datetime import date

import pytest

from infra.aws.epoch5_daily_audit import reconcile
from stocklens import paper


def sample():
    state = paper.new_state()
    start = paper.new_state()
    day = date(2026, 11, 27).isoformat()
    prices = {"QQQ": 600., "TQQQ": 40.}
    market = paper.SessionMarket(day, prices, prices, prices, {}, {})
    signal = {"latest": {"asof_date": "2026-11-25", "qqq_weight": .861875,
                         "tqqq_weight": .123125, "level": 1, "target_leverage": 1.25,
                         "defense_active": False}, "action": "NO_CHANGE"}
    trades = paper.rebalance_if_required(state, signal, market, True)
    row = paper.mark_session(state, signal, market, trades, {"dividends_credited": 0}, True)
    return {"start_state": start, "row": row, "state": state, "trades": trades, "session": day}


def test_reconstructs_genesis_fills():
    reconcile(sample())


@pytest.mark.parametrize("field", ["equity", "cash", "qqq_shares", "cumulative_fees", "cumulative_slippage_cost"])
def test_drift_fails_closed(field):
    p = sample()
    p["row"][field] += 1
    with pytest.raises(ValueError):
        reconcile(p)

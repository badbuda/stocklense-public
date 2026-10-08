import pytest
from broker_failure_harness import Sandbox, Intent, FailClosed, selfcheck


def order(key="x", symbol="QQQ", side="BUY", qty=2, price=100.,
          signal="2026-10-07", session="2026-10-08"):
    return Intent(key, symbol, side, qty, price, signal, session)


def test_idempotency_duplicate_request_no_double_debit():
    broker = Sandbox(cash=1000)
    a = broker.submit(order())
    b = broker.submit(order())
    assert a == b
    assert broker.cash == 1000
    broker.fill("x", 1, 101)
    assert broker.cash == 899
    assert broker.positions["QQQ"] == 1
    assert broker.submit(order())["filled"] == 1
    with pytest.raises(FailClosed, match="IDEMPOTENCY_KEY_COLLISION"):
        broker.submit(order(symbol="TQQQ"))


def test_partial_fill_reject_and_overfill():
    broker = Sandbox()
    broker.submit(order())
    broker.fill("x", 1, 101)
    with pytest.raises(FailClosed, match="INVALID_FILL"):
        broker.fill("x", 2, 101)
    broker.fill("x", 1, 99)
    assert broker.orders["x"]["receipt"]["status"] == "FILLED_LOCAL_ONLY"
    with pytest.raises(FailClosed, match="INVALID_FILL"):
        broker.fill("x", 1, 99)
    broker.submit(order("y"))
    assert broker.reject("y")["status"] == "REJECTED_LOCAL_ONLY"
    with pytest.raises(FailClosed, match="INVALID_FILL"):
        broker.fill("y", 1, 99)


def test_fail_closed_on_stale_signal_order_types_and_cap():
    broker = Sandbox(cash=1000, max_notional=500)
    for case in (order(signal="2026-10-08"),
                 order(symbol="NVDA"), order(side="SHORT"),
                 order(qty=0), order(price=-1),
                 order(qty=10, price=100)):
        with pytest.raises(FailClosed):
            broker.submit(case)
    assert broker.orders == {}


def test_kill_switch_blocks_new_orders_and_fills():
    broker = Sandbox()
    broker.submit(order())
    broker.kill()
    with pytest.raises(FailClosed, match="KILL_SWITCH_ACTIVE"):
        broker.submit(order("z"))
    with pytest.raises(FailClosed, match="KILL_SWITCH_ACTIVE"):
        broker.fill("x", 1, 100)


def test_cash_positions_and_reconciliation():
    broker = Sandbox(cash=1000)
    broker.submit(order(qty=2))
    broker.fill("x", 2, 100)
    assert broker.reconcile(800, {"QQQ": 2, "TQQQ": 0})
    assert not broker.reconcile(799, {"QQQ": 2, "TQQQ": 0})
    with pytest.raises(FailClosed, match="INSUFFICIENT_SHARES"):
        broker.submit(order("sell", side="SELL", qty=3))
    broker.submit(order("sell", side="SELL", qty=2))
    broker.fill("sell", 2, 99)
    assert broker.reconcile(998, {"QQQ": 0, "TQQQ": 0})


def test_selfcheck_never_claims_external_broker(tmp_path):
    report = selfcheck(str(tmp_path / "report.json"))
    assert report["status"] == "PASS"
    assert report["broker_connected"] is False
    assert report["live_trading_authorized"] is False
    assert all(report["tests"].values())

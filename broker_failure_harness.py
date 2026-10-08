"""Deterministic LOCAL broker-failure simulator. It has NO network/API/live connector."""
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path


@dataclass(frozen=True)
class Intent:
    key: str
    symbol: str
    side: str
    quantity: int
    price: float
    signal_date: str
    session_date: str


class FailClosed(Exception):
    pass


class Sandbox:
    def __init__(self, *, cash=10000., max_notional=2000.):
        self.cash = float(cash)
        self.max_notional = float(max_notional)
        self.positions = {"QQQ": 0, "TQQQ": 0}
        self.orders = {}
        self.killed = False

    def kill(self):
        self.killed = True

    def submit(self, order: Intent):
        if self.killed:
            raise FailClosed("KILL_SWITCH_ACTIVE")
        if (not order.key or order.symbol not in self.positions or
                order.side not in ("BUY", "SELL") or
                type(order.quantity) is not int or order.quantity <= 0 or
                not 0 < order.price < 1e9 or order.signal_date >= order.session_date):
            raise FailClosed("INVALID_ORDER")
        if order.key in self.orders:
            prior = self.orders[order.key]
            if prior["intent"] != order:
                raise FailClosed("IDEMPOTENCY_KEY_COLLISION")
            return prior["receipt"]
        if order.quantity * order.price > self.max_notional:
            raise FailClosed("MAX_NOTIONAL_EXCEEDED")
        if order.side == "BUY" and order.quantity * order.price > self.cash:
            raise FailClosed("INSUFFICIENT_CASH")
        if order.side == "SELL" and order.quantity > self.positions[order.symbol]:
            raise FailClosed("INSUFFICIENT_SHARES")
        receipt = {"key": order.key, "status": "ACCEPTED_LOCAL_ONLY",
                   "requested": order.quantity, "filled": 0, "remaining": order.quantity}
        self.orders[order.key] = {"intent": order, "receipt": receipt.copy()}
        return receipt.copy()

    def fill(self, key, quantity, actual_price):
        if self.killed:
            raise FailClosed("KILL_SWITCH_ACTIVE")
        if key not in self.orders:
            raise FailClosed("UNKNOWN_ORDER")
        rec = self.orders[key]
        intent = rec["intent"]
        receipt = rec["receipt"]
        if (type(quantity) is not int or quantity <= 0 or
                quantity > receipt["remaining"] or
                not 0 < actual_price < 1e9):
            raise FailClosed("INVALID_FILL")
        amount = quantity * actual_price
        if intent.side == "BUY":
            if amount > self.cash:
                raise FailClosed("INSUFFICIENT_CASH_ON_FILL")
            self.cash -= amount
            self.positions[intent.symbol] += quantity
        else:
            if quantity > self.positions[intent.symbol]:
                raise FailClosed("INSUFFICIENT_SHARES_ON_FILL")
            self.cash += amount
            self.positions[intent.symbol] -= quantity
        receipt["filled"] += quantity
        receipt["remaining"] -= quantity
        receipt["status"] = "PARTIAL_LOCAL_ONLY" if receipt["remaining"] else "FILLED_LOCAL_ONLY"
        return receipt.copy()

    def reject(self, key):
        if key not in self.orders:
            raise FailClosed("UNKNOWN_ORDER")
        receipt = self.orders[key]["receipt"]
        if receipt["filled"]:
            raise FailClosed("REJECT_AFTER_PARTIAL_REQUIRES_CANCEL")
        receipt["status"] = "REJECTED_LOCAL_ONLY"
        receipt["remaining"] = 0
        return receipt.copy()

    def reconcile(self, expected_cash, expected_positions):
        return (abs(self.cash - expected_cash) < 0.000001
                and self.positions == expected_positions)


def selfcheck(out="docs/broker_failure_harness.json"):
    a = Sandbox()
    order = Intent("k1", "TQQQ", "BUY", 4, 100., "2026-10-07", "2026-10-08")
    assert a.submit(order)["status"] == "ACCEPTED_LOCAL_ONLY"
    assert a.submit(order)["remaining"] == 4
    assert a.fill("k1", 2, 101.)["status"] == "PARTIAL_LOCAL_ONLY"
    assert a.fill("k1", 2, 102.)["status"] == "FILLED_LOCAL_ONLY"
    assert a.reconcile(9594., {"QQQ": 0, "TQQQ": 4})
    failed = {}
    for name, fn in (
        ("duplicate_key_collision", lambda: a.submit(Intent("k1", "QQQ", "BUY", 1, 99., "2026-10-07", "2026-10-08"))),
        ("excess_position_sale", lambda: a.submit(Intent("k2", "TQQQ", "SELL", 5, 100., "2026-10-07", "2026-10-08"))),
        ("max_notional", lambda: a.submit(Intent("k3", "QQQ", "BUY", 100, 100., "2026-10-07", "2026-10-08"))),
        ("reconciliation_drift", lambda: (_ for _ in ()).throw(FailClosed("RECONCILIATION_MISMATCH")) if not a.reconcile(10000., {"QQQ": 0, "TQQQ": 4}) else None),
    ):
        try:
            fn()
        except FailClosed:
            failed[name] = True
    a.kill()
    try:
        a.submit(Intent("k4", "QQQ", "BUY", 1, 100., "2026-10-07", "2026-10-08"))
    except FailClosed:
        failed["kill_switch"] = True
    assert len(failed) == 5
    report = {"schema_version": 1, "status": "PASS", "mode": "LOCAL_SIMULATOR_ONLY",
              "broker_connected": False, "broker_fills_observed": False,
              "live_trading_authorized": False, "tests": failed,
              "no_real_orders_sent": True,
              "note": "Local contract selfcheck only, not an external broker sandbox qualification."}
    path = Path(out);path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    print(json.dumps(selfcheck()))

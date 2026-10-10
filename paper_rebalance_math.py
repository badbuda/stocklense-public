"""Shared deterministic target sizing / band check for frozen StockLens paper.

Pure math; uses supplied prices only. Never estimates broker executions.
"""
from __future__ import annotations
import math

SYMBOLS = ("QQQ", "TQQQ")
TOLERANCE = 0.005  # 50 basis points; strictly a paper noise filter


def _validate(weights, prices, equity):
    if not math.isfinite(float(equity)) or float(equity) <= 0:
        raise ValueError("INVALID_REBALANCE_EQUITY")
    if set(weights) != set(SYMBOLS) or set(prices) != set(SYMBOLS):
        raise ValueError("INVALID_REBALANCE_SYMBOLS")
    for s in SYMBOLS:
        w, px = float(weights[s]), float(prices[s])
        if not math.isfinite(w) or w < 0 or w > 1:
            raise ValueError("INVALID_REBALANCE_WEIGHT:" + s)
        if not math.isfinite(px) or px <= 0:
            raise ValueError("INVALID_REBALANCE_PRICE:" + s)
    if sum(float(weights[s]) for s in SYMBOLS) > 1.000001:
        raise ValueError("OVERINVESTED_REBALANCE")


def target_shares(weights, equity, prices):
    """Floor to whole shares at a provided point-in-time reference price."""
    _validate(weights, prices, equity)
    return {s: math.floor(float(weights[s]) * float(equity) / float(prices[s]))
            for s in SYMBOLS}


def weight_gap(holdings, weights, prices, equity):
    """Absolute weight error at one reference time, not broker fill parity."""
    _validate(weights, prices, equity)
    return max(abs(int(holdings[s]) * float(prices[s]) / float(equity)
                   - float(weights[s])) for s in SYMBOLS)


def within_band(holdings, weights, prices, equity, tolerance=TOLERANCE):
    if not math.isfinite(tolerance) or tolerance < 0 or tolerance > 1:
        raise ValueError("INVALID_REBALANCE_TOLERANCE")
    return weight_gap(holdings, weights, prices, equity) <= tolerance

"""FREE QuantConnect chart transport for original frozen LEAN decision inputs.

Attach to a COPY of the native SL724 LEAN algorithm, after its decision has
already been made from original LEAN data. No SetHoldings, no MarketOrder,
no independent feature computation, and no alternate replay.

Seven extra series + three pre-existing SL724 Leverage/NAV/Drawdown = 10
custom series; each is <= 3,774 points (Free quota: 10 / 4,000).
Check chart quota before use if the original project contains other plots.
"""
from __future__ import annotations
import math

CHART = "SL724_P0_FEATURES"
COLUMNS = ("close", "sma50", "sma200", "vol20", "mom12", "level", "defense")


class LeanChartFeatureExporter:
    def __init__(self):
        self.rows = 0

    def record(self, algorithm, *, close, sma50, sma200, vol20, mom12, level, defense):
        # Keep original values used by LEAN, NOT values recomputed elsewhere.
        data = {
            "close": close, "sma50": sma50, "sma200": sma200,
            "vol20": vol20, "mom12": mom12, "level": level,
            "defense": 1.0 if defense else 0.0,
        }
        plot = getattr(algorithm, "plot", None) or getattr(algorithm, "Plot", None)
        if plot is None:
            raise RuntimeError("LEAN_PLOT_NOT_AVAILABLE")
        for key in COLUMNS:
            value = float(data[key])
            if not math.isfinite(value):
                raise ValueError("NONFINITE_NATIVE_LEAN_FEATURE:" + key)
            plot(CHART, key, value)
        self.rows += 1

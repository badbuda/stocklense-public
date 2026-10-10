# StockLens 7.24 P1 original results — October 10 2026

All calculations below used private user-supplied QuantConnect simulation results. Original raw data and daily positions remain private. No broker trades or live orders were performed.

Original backtest and P1 portfolio observer contain 3,774 exactly timestamp-aligned NAV/portfolio sessions, 345 simulated filled orders and 301 closed-trade economic records. The original model charts and statistical reports were unchanged. Economic order attributes were also unchanged; 1,028 numeric fields had harmless JSON floating-point representation differences (maximum relative 3.87e-15), not transaction changes.

For every simulated day, replaying all signed native QQQ, QLD, and TQQQ order quantities reproduced all 11,322 observed ETF share states, with no discrepancies. There were 179 monthly $3,500 deposits, for a cumulative $726,500 of contributions including the $100,000 initial capital.

On 3,774 dates, dividing native chart equity by chart NAV units matched the original native chart NAV within its displayed precision; worst absolute discrepancy 0.0000497. Original native simulated cash, signed order values and contributions implied a total fee of $42,291.92549 versus $42,291.93 reported by QuantConnect (difference $0.00451, attributable to report rounding). Every no-trade date had zero unexplained cash movement. Per-order fees were not separately exported; original model fees use the security price, which can differ from execution fill price.

**Important boundary:** The native P1 chart ends on 2024-08-29, when simulated equity was $33,687,393.62. Original backtest end-of-run statistics reflect 2024-08-30 (last exchange session under end date 2024-08-31) and report $34,817,008.35. This is a DIFFERENT date. The observer contains no plotted 2024-08-30 portfolio state; therefore original run-end equity/holdings chart parity remains blocked, not failed or proven.

This closes internal simulated LEAN order/share/cash/chart consistency for 3,774 observed dates; it does not prove independent Python same-start portfolio parity, unrounded original source authenticity, true market NBBO, broker fills, a statistically significant edge, or readiness to trade capital. Frozen StockLens 8.0 remains unchanged. Reproduce the private account checks with `qc_p1_native_order_ledger_audit.py` using the two private original/observer Results JSONs; see P1 runbook and regression tests.

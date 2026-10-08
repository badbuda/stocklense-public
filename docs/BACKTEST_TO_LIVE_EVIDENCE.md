# StockLens 8.0 — Backtest to Live Acceptance Contract

**RESEARCH AND FORWARD PAPER ONLY. LIVE BROKER ORDERS ARE NOT AUTHORIZED.**

A green CI, high historical CAGR, or a 63-session sample is never proof of future returns.

## Evidence ladder

| Stage | What it verifies | What it cannot verify |
|---|---|---|
| Observed QQQ/TQQQ adjusted OHLC | Frozen decisions, next-session modeled open, historical ETF drawdowns | 09:31/09:32 fills, spread, live liquidity |
| Independent price vendor + immutable raw snapshots | Corporate actions, revisions, temporal availability, source integrity | Order execution and statistical independence |
| Same-run original LEAN export | Canonical equity, orders, fills, contributions, code/data identity | Broker live fills or strategy future profitability |
| Out-of-sample and adverse robustness | Fragility, sensitivity, holdout selection bias, bad market regimes | Guaranteed persistence of alpha |
| Truly prospective frozen 8.0 paper | Timestamped signals, real-time capture without filling missed days | Broker fills or model selection independence |
| Broker sandbox | Idempotency, rejection, partial fills, reconnect, position reconciliation, kill switch | Market alpha |
| Human-authorized micro pilot | Real implementation costs, operations and partial real fills | Profit guarantee |

## Non-negotiable research rules

1. For all NEW return and drawdown research use **observed QQQ and TQQQ prices**, not QQQ returns multiplied by a leverage factor. Older synthetic results remain archived only.
2. Real TQQQ begins in February 2010. Both portfolio paths must use the same available dates, starting capital, monthly contributions, and actual traded ETF prices.
3. Compute the frozen 8.0 signal from QQQ data available by the LAST completed market close. Execute strictly in the NEXT available session. Verify by perturbing later data and requiring identical earlier NAVs.
4. Current historical fill assumption is adjusted daily OPEN — explicitly a proxy, not 09:31 reduction or 09:32 addition fills. Exact execution requires minute-bar evidence or actual fills.
5. Missing ETF bars, unknown split adjustments, nonfinite/nonpositive prices, future-signal leakage, negative cash, inconsistent SHA evidence or wrong-epoch data must stop publication.
6. Include invested cash fraction (98.5%), whole shares, commission per side, slippage per side, target exposure transitions, contributions, tax and currency considerations, and liquidity constraints.
7. Publish the source timestamp, instrument, adjustment policy, frozen model fingerprint, code and data SHA, cohort range, day-by-day evidence, and explicit uncertainty.

## Distinguishing backtest, shadow, paper and live

- **Backtest**: historical counterfactual with known prices. It can reproduce rules and reveal failures, but is biased by parameter/holdout reuse and approximate execution.
- **Shadow signal**: timestamped contemporaneous instruction, no shares or orders. It proves only that the decision engine ran at the correct time.
- **Paper**: simulated orders against data available AFTER the decision, with positions and cash. Missing intraday data creates an explicit gap; never silently backfill a prospective trade.
- **Live**: broker order submission, rejects, spreads, fills, partial fills, latency, corporate actions, taxes, transfers, custody and regulation. A different level of evidence and operational risk.

## Falsification and statistical checks to close

- Re-run original LEAN from exact same code and data; require immutable daily equity, orders, fills, cashflow exports. No synthetic reconstruction can substitute for that file.
- Audit every tested variant, rejected experiment, multiple-comparison family and reused holdout. Reused validation periods cannot count as fresh out-of-sample evidence.
- Validate a second independently sourced point-in-time QQQ/TQQQ price vendor; fingerprint raw files; reconcile split/dividend events and revisions.
- Test every frozen exposure level: cash, 1.25x blend, 2x blend, 3x actual TQQQ. No synthetic price fallback.
- Falsify with delayed trading, 0–50bps slippage, higher fees, suspensions, gap opens, low-liquidity and bad-regime windows; report drawdown recovery and percent of rolling windows below QQQ.
- Audit fully paired prospective frozen 8.0 paper sessions against QQQ and real ETF historical close/open paths, with attribution to timing, slippage, cash, fees, shares and ETF-price differences.
- Reach 63 and then 252 real, timestamp-validated paired sessions for **reviews**. This does not guarantee expected future return or by itself authorize deployment.
- Independently test sandbox broker idempotency, duplicates, rejects, reconnect, partial fills, reconciliation and kill switch.
- Human review and explicit loss budget, investment account constraints, risk tolerance, jurisdiction and tax approval before any real-money pilot.

## Current evidence and automatic blocking

Machine-readable state: docs/backtest_live_readiness.json. Real ETF backtest:
research/tradable_tqqq_execution_comparison.json. Real ETF path risk:
research/observed_tqqq_risk_audit.json. Prospectively recorded sessions:
docs/paper_forward_audit.json. Causality tests:
tests/test_real_tqqq_causality_adversarial.py.

Raw original LEAN exports, independently verified vendor snapshots, paired
prospective sessions, broker sandbox credentials and human trading authorization
cannot be fabricated by a program. Their absence must remain BLOCKED.

**Deployment rule:** pass reproducibility and causality → independent raw inputs
→ independent historical selection audit → legitimate forward paper + benchmark
→ broker sandbox and risk review → separate, explicit human approval for a tiny
pilot. No automatic promotion and no live orders from CI.
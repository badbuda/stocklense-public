# StockLens 8.0 — Independent Live Readiness Plan

Status: **BLOCKED FOR REAL-MONEY TRADING** until external execution and independent forward evidence are verified. Frozen 8.0 remains unchanged. Do not automatically submit orders or authorize funding.

## What the backtest can establish

The active research protocol uses observed, adjusted QQQ and TQQQ prices, never synthetic 3x QQQ returns. Eligible tests begin at TQQQ's actual 2010 inception and apply the **prior completed close** decision to next-session **adjusted daily OPEN**. The daily OPEN is a research execution proxy, **not** an observed 09:31/09:32 fill.

Historical CAGR, compounded equity and drawdown are descriptive. They do not establish tradability, statistical independence, account-specific return, tax treatment or future profitability. The 2009 QQQ-times-leverage reports are **archival only**. The actual ETF comparison is the primary report.

## Ordered evidence gates

1. **Source integrity:** frozen QQQ decision rules, observed TQQQ/QQQ OHLC, matched sessions, no TQQQ backfill before inception, hash-stamped data and failures for missing/suspicious prices. Pass only with independent vendor crosscheck, immutable raw snapshots, split/dividend/timestamp verification and stale-bar detection.
2. **Model-selection audit:** inventory candidate configurations and tuning cycles, collect all tested variants, identify holdout reuse, point-in-time assumptions and multiple-testing bias. No post-hoc 5-year result may be called untouched validation.
3. **Independent reproducibility:** obtain a **single original QuantConnect/LEAN run's** source SHA, parameters, precise cashflow ledger, 3,774 daily rows, 345 orders/fills and equity, then compare same-input outputs. A screenshot of a final equity number is insufficient.
4. **Executable exposure:** model 09:31 reductions and 09:32 additions with historical minute bars available at the decision timestamp. Preserve no-lookahead. Validate whole shares, cash, intraday gap, volumes, order types, dynamic spread/slippage, dividends, splits, halts, and rejected/partial fills. Model QQQ/TQQQ only. Live broker fills still differ from simulated fills.
5. **Adversarial tests:** matched QQQ after costs and tax assumptions; high-fee and unfavorable spread ladders; additional 1–2-session decision delays; 2020 and 2022 crisis slices; price-source perturbations, leave-one-crisis-out, and alternative open proxies. Report unfavorable results. No synthetic leverage as current decision evidence.
6. **Forward trial:** immutable signal snapshots and daily paper equity from live timestamps, with prospective orders and audit trail; compare measured paper P&L against replay and QQQ on the **same dates**. Record failures and missed sessions rather than backfilling. Exploratory checkpoints: 63 paired sessions for initial reliability review, 252 for extended study; **neither proves future performance**. The eight observed sessions of SL9-007 are a *different challenger*, not a frozen-8.0 paper track.
7. **Broker sandbox:** test sandbox or read-only integration with idempotency, kill switch, reconciliation, partial fills, timeouts, duplicate requests, stale data, DST/holidays, corporate actions and degraded market behavior. No real order calls in CI.
8. **Risk and permissions:** define user-owned loss budget, maximum drawdown tolerance, order-size/notional limits, concentration and gap risk, available capital, legal/broker terms and explicit human authorization. No automatic model promotion or capital scaling.

## Behavioral difference: backtesting vs forward/paper vs real

| Layer | Price and decisions | What it misses |
|---|---|---|
| Backtest | Historic adjusted daily OPEN after previous-close signal | Real spreads, 09:31/09:32 fills, outages, survivorship/selection bias, unobserved behavior |
| Forward paper | Decisions timestamped as they happen, modeled or minute-bar hypothetical fills | Actual exchange queue priority, broker execution, funding constraints |
| Broker sandbox | API handling and failure cases | Real market slippage and liquidity |
| Tiny, explicitly approved live pilot | Broker-confirmed fills, position and cash reconciliation | Cannot guarantee profits or remove leveraged ETF tail risk |

Any claim of live readiness must be derived from verified evidence, not from backtest annual returns or green CI. `docs/backtest_live_readiness.json` is the machine-readable checklist; its BLOCKED status is intentional until evidence exists. The system remains shadow/paper only.

# StockLens 8.0 — independent two-question audit (2026-10-10)

## Evidence and reproducibility

- Research CI: [Fast Guard #57](https://github.com/badbuda/stocklense-public/actions/runs/38047790535) — **313/313 tests PASS**. Same run executes `python observed_etf_two_question_audit.py`, requires unchanged frozen-baseline NAV endpoint and max-drawdown parity, and uploads [the complete JSON and Hebrew report](https://github.com/badbuda/stocklense-public/actions/runs/38047790535/artifacts/11668556763).
- Input: `docs/portal-history.json` as of 2026-10-09, observed Yahoo adjusted QQQ and TQQQ daily OHLC, **4,191 sessions**, 2010-02-11 through 2026-10-09. No synthetic TQQQ price series. `snapshot_sha256` is preserved in the machine-readable artifact.
- Simulated **next-session daily OPEN** execution, whole-share QQQ/TQQQ positions, 2 bps modeled fee plus 10 bps modeled slippage per side; no observed 09:31/09:32 bid-ask, no broker fills. The frozen StockLens path is independently reproduced; model 8.0 rules remain unchanged.
- Risk-matched **static** benchmarks select ETF weights **only from 2010–2017** (existing historically reused training sample). Monthly static-mix rebalance at observed ETF daily open. This is a counterfactual risk explanation, not a clean, prospectively registered holdout.
- The historical model, thresholds, validation and 2023+ observational years were previously inspected. **Do not** claim statistical independence or a newly pristine holdout.

## Question 1: Is all apparent performance just Nasdaq leverage?

Full 2010–2026 sample (no deposits; simple CAGR; drawdown from peak):

| Portfolio | CAGR | MaxDD | Annual realized vol |
|---|---:|---:|---:|
| Frozen StockLens 8.0 | **40.03%** | **−49.08%** | 46.96% |
| 98.5% QQQ and cash, monthly | 19.45% | −34.65% | 20.31% |
| **Development-volatility-matched** 78.8% TQQQ + 19.7% QQQ + 1.5% cash | **39.73%** | **−74.91%** | 51.71% |
| **Development-beta-matched** 70.92% TQQQ + 27.58% QQQ + 1.5% cash | **38.11%** | **−72.07%** | 48.45% |
| 98.5% TQQQ and cash, monthly | 43.28% | −81.05% | 60.07% |

**Interpretation:** historical terminal return was almost reproducible with static, predominantly leveraged ETF exposure. But the frozen strategy avoided around **25.8 percentage points** of the full-sample maximum peak-to-trough drawdown compared with the volatility-calibrated static mix, while achieving similar CAGR. This is evidence of **historical regime-timing/risk-profile differences**, not decisive proof of future alpha. The static comparator is calibrated in 2010–17; its realized **full-period** volatility (51.7%) is no longer equal to StockLens (47.0%), so do not describe this as a full-period precisely volatility-matched experiment.

With no risk-free adjustment, daily QQQ CAPM-style OLS estimate:
- Beta to QQQ **1.991**.
- Arithmetic annualized alpha **+4.49 percentage points**.
- Newey–West/HAC-21 t-stat **0.806** and descriptive 95% interval **[−6.43%, +15.41%]** annualized.
- Neither this CI nor 21/63-day block resampling accounts for the full model search/selection. **Cannot reject alpha=0 on this evidence; do not claim economically reliable, statistically proven independent alpha.**

### Transfer: training, reused validation, reused later years

| Historical interval | StockLens CAGR / MaxDD | Static development-vol-matched CAGR / MaxDD | Reading |
|---|---|---|---|
| 2010–2017 development | 34.62% / −49.08% | **45.77% / −38.39%** | Static benchmark **wins both**; model not universally superior |
| 2018–2022 reused validation | **27.69% / −48.59%** | 11.43% / −74.91% | Model historically preserves much more capital through adverse regimes |
| 2023–2026 reused observational | 71.35% / −45.33% | 71.26% / −51.55% | Nearly identical growth; frozen model has smaller drawdown |

The result is **conditional on regime and period**. These periods do **not** constitute genuinely unseen testing after extensive research.

## Question 2: Can we cut drawdowns materially while keeping most growth?

Only capped overlays were tested; they *never increase* frozen leverage. All trigger on **prior-session** Yahoo QQQ adjusted closes, are traded in the independent next-daily-OPEN whole-share simulator, and pay estimated fee/slippage.

| Scenario | CAGR | Full-period MaxDD | Δ CAGR vs frozen | Δ MaxDD (higher is better) |
|---|---:|---:|---:|---:|
| Frozen 8.0 | **40.03%** | −49.08% | — | — |
| Fixed vol tiers (prior 20d RV >32% / >42%) | 39.87% | −49.08% | **−0.16pp** | essentially zero |
| Fixed 5-day QQQ shock pulse, cap at 2x | 38.58% | −49.07% | **−1.45pp** | **~0.001pp** |
| Combined tier + shock | 38.58% | −49.07% | **−1.45pp** | **~0.001pp** |

**Do not promote any of these variants.** In the full sample, the volatility-tier overlay intervenes on just **one session**, because the frozen strategy generally already adjusts when QQQ volatility is extreme. A 5-day shock intervention on 45 sessions **does not materially prevent the worst drawdown**.

Lag stress at the same modeled 10bps slippage:
- Shock overlay at lag 0: **38.58% CAGR, −49.07% MaxDD**.
- At lag 1: **39.70% CAGR, −49.75% MaxDD**.
- At lag 2: **38.94% CAGR, −52.92% MaxDD** — **worse drawdown than the frozen baseline**.
- The combined cap exhibits similar deterioration at lag 1/2, demonstrating why an attractive lag-0 backtest alone is inadequate.

Earlier, differently implemented close-return research found a *continuous volatility target* (60%/RV20 cap) could improve drawdown by around **3.7pp** at roughly **−1.16pp CAGR** under its **different** accounting/execution assumptions. This is a **research lead only**, not an apples-to-apples validated improvement under the present whole-share/open-price/cost model; it must be retested here before acceptance. The earlier sparse pulse champion also failed lag robustness.

### Volatility drag: regime-conditional observations, not trade signals

Classify *next-session* TQQQ and QQQ **observed adjusted-close log returns** using the *prior completed* QQQ 20-session realized annualized volatility. These are conditional historical averages, not forecasts.

| Prior 20d QQQ volatility | Sessions | QQQ ann. mean log growth | TQQQ ann. mean log growth | TQQQ minus 3×QQQ log gap |
|---|---:|---:|---:|---:|
| below 25% | 3,246 | +18.4% | +42.0% | **−13.1pp** |
| 25–35% | 539 | +7.6% | **−8.2%** | **−31.1pp** |
| above 35% | 205 | +32.0% | +30.9% | **−65.1pp** |

**Implication:** volatility drag gets harsher in volatile regimes; nonetheless, days following the **highest-volatility** conditions included powerful rebounds in both QQQ and TQQQ. Automatically getting out and re-entering late can lose those rebounds, as seen in the lagged overlay experiment. A conditional signal is not sufficient without reentry mechanics, executable prices and validation.

## Decisions and next falsifications

1. **Keep frozen StockLens 8.0 unchanged**; no automatic overlay promotion, no broker instructions, no real-capital authorization.
2. The historical model appears to offer **risk management relative to a heavily levered static allocation**, but not a proven independent risk-adjusted alpha after considering selection/search bias and extreme strategy drawdowns.
3. **No tested new simple guard is robust enough** under this next-OPEN/whole-share model to claim a material drawdown improvement without significant cost to return.
4. Next experiment, still research-only: adapt the previously investigated *continuous volatility target + ramped re-entry / minimum hold* to this **same** next-open execution engine; stress 0/1/2 session delays, 10/20/30 bps, leave-one-crisis-out, power/selection sensitivity. Benchmark against frozen rather than treat it as a replacement.
5. Continue fresh prospective paired sessions (only 2 frozen Paper as of this audit), original QuantConnect/LEAN same-input daily exports, and independent timestamped NBBO/broker evidence. None can be generated retroactively.

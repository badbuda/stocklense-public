# StockLens × TQQQ/SQQQ video — exploratory additive overlays (10 Nov 2026)

**Status:** historical falsification research only, no automatic promotion, no PROD/AWS/broker changes. **This protocol and its parameters were formalized after exploratory results were seen**; do not claim prospective preregistration, fresh holdout, independent evidence, or a clean statistical discovery.

## Claims evaluated / missing data

The source video suggests (1) stop or reduce TQQQ around QQQ SMA50; (2) use SMA20 vs SMA50 to time "buy the dips"; (3) allocate 10% of a *separate trading account* daily to TQQQ, take ~0.5% profit, and exit most positions within 3–5 sessions; (4) buy SQQQ intraday when the first ~30–45 minutes and prior-day lows imply a bear day, asserting ~80% directional accuracy.

Only (1)–(3) admit a daily adjusted open/close research proxy with available verified **real observed** QQQ/TQQQ snapshot. The source does **not** include intraday high/low or 1/5/30-minute QQQ/SQQQ observations. The 0.5% limit fills, first-half-hour predictors, last-hour reversals, previous-day high/low and supply zones **cannot be backtested faithfully here**. The cited 80% prediction claim is not verified; do not substitute fictional SQQQ -3x QQQ daily returns.

## Fixed exploratory replay definitions

Source: \`research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json\`, recorded SHA \`bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129\`; 4,191 sessions 2010-02-11–2026-10-09, StockLens 8.0 immutable historical decision \`l\`. Every open uses that **already prior-close-derived** level; optional *additional* lag 0/1. SMA20/SMA50 computed only on completed QQQ closes before the trading open (50-session warmup within the frozen sample).

* Frozen control: unchanged QQQ/TQQQ whole-share allocation, target invested fraction 98.5%.
* \`50_half_premium\`: below SMA50 halve excess exposure over 1x (e.g. 3x → 2x, 2x → 1.5x). Frozen 0x defense preserved.
* \`50_cap_125\`: below SMA50, cap at 1.25x.
* \`20x50_cap_125\`: if SMA20 below SMA50, cap 1.25x.
* \`both_50_20x50\`: both negative → cap 1.25x; either negative → cap 2x.
* \`50_no_upshift\`: when QQQ below SMA50, block leverage increases but permit reductions and exit-to-zero.
* Sleeve experiments: keep 80% initial capital in a separately funded frozen StockLens core and 20% in a sleeve, without implicit borrowing. Controls: leave that 20% as cash, or buy/hold real TQQQ in that slice. Swing sleeve admits one new lot each eligible open at **10% of current sleeve account equity**, at most five live lots; sell only at the next daily open after a **prior completed close** indicates ≥0.5% gain and at least 3 sessions have passed, or exit at 5 sessions regardless. Modes: ungated, SMA50-gated, SMA50 + 20/50 gated, and SMA50-gated with half-premium cap on the frozen core. This is explicitly **not** the video’s intraday limit-fill logic.
* Primary stress: extra lag 1, 10bps slippage per side, 2bps fee per side, $100,000 initial account, no deposits, simple adjusted daily OPEN whole-share executions. Other stresses: lag 0/1 × slippage 10/20bps/side. No taxes, FX, spread measurements, intraday fills, cash interest or exact client brokerage tariffs.
* No parameter tuning based on subperiods, and no promotion based on these reused observations.

## Exploratory findings, primary stress (extra lag1 / 10bps)

| Variant | CAGR | MaxDD | Δ CAGR versus 100% frozen |
|---|---:|---:|---:|
| Frozen StockLens 8.0 | 37.50% | -50.12% | reference |
| Halve leverage premium below SMA50 | 33.39% | -49.35% | -4.11pp |
| Cap 1.25x below SMA50 | 30.40% | -48.55% | -7.10pp |
| Cap 1.25x when SMA20 < SMA50 | 29.29% | -51.80% | -8.21pp |
| Combined 50 / 20×50 caps | 29.75% | -50.18% | -7.75pp |
| Block upshifts below SMA50 | 37.46% | -55.00% | -0.04pp |
| 80% core + 20% cash | 35.68% | -49.45% | -1.82pp |
| 80% core + 20% TQQQ buy/hold | 39.10% | -64.40% | +1.60pp |
| 80% core + 20% swing (no filter) | 35.75% | -49.49% | -1.75pp |
| 80% core + 20% swing above SMA50 | 35.70% | -49.36% | -1.80pp |
| 80% core + 20% swing + SMA20/50 | 35.69% | -49.47% | -1.81pp |
| 80% core + 20% swing + SMA50 core cap | 31.66% | -46.79% | -5.84pp |

The ungated swing generated 4,136 closed round trips, with ~64.7% nominal modeled net-of-friction win rate, but only marginal benefit over 80% frozen + 20% cash and underperformed full StockLens. High win rate ≠ high expectancy or net compounding. The 20% buy-and-hold TQQQ alternative raised CAGR but worsened drawdown by ~14.3pp.

Across the 0/1-lag × 10/20bps stress grid, **no risk filter or sleeve produced a robust improvement in both CAGR and MaxDD relative to frozen 100%**. The conservative extra lag matters; the same historical series has already been explored extensively.

## Next evidence required (blocked, not silently approximated)

1. Obtain real minute-level QQQ, TQQQ and SQQQ bars (opening range, yesterday high/low, order timing, spread/queue/partial fills) before testing short-side / "80%" / 0.5% intraday profit limits. Require precise rule definition and leak-free 09:30–10:15 ET timestamps.
2. Add realized tax lots and verified Israeli NIS FX / broker withholding to frequent turnover; no inference from gross trades. Use \`docs/AFTER_TAX_STOCKLENS_RESEARCH.md\` and \`research/tax_deferral/README.md\`.
3. If future data show an advantage, compare sleeves against matched-risk / equal-cash controls and clean prospective paper, not just StockLens 100%.
4. Keep StockLens 8.0 frozen; only isolated ST experiments may proceed with explicit validation.

Reproducibility: \`python research/video_tqqq_sqqq_overlay.py\`; outputs \`research/results/video_tqqq_sqqq_overlays_20261110.json\`. Explicitly does not authorize paper/PROD/broker execution.

# StockLens — incremental layers on top of Frozen 8.0 (2^4 factorial)
**Date:** 2026-11-10  
**Status:** Research replay passed GitHub Actions CI; not a promoted strategy, no orders and no ST/PROD mutations.

## Exactly what this test does
Runs **16 configurations**: Frozen 8.0; each one of four independent new overlays; all six pairs; all four triples; all four together. Target leverage on decision-day `i` is always:
`min(FROZEN_8_target[i], each_selected_overlay_cap_from_completed_session[i-1])`.

Overlays tested as *research interpretations* rather than original-author source:
- LRS: QQQ 200-session SMA hysteretic (entry above +1%, exit below -1%), cap to **cash** on risk-off.
- RSI: 7-session QQQ RSI below 25 -> cap at **1.25x**.
- MACD: QQQ MACD(6,13,5) line below signal -> cap at **2x**.
- TSI_EMA: TQQQ below EMA8 or TSI(25,13,7) below its signal -> cap at **1.25x**. Not the complete Autopilot trading rules.

This is a pure on-top risk reduction; no overlay is allowed to increase baseline leverage, and no frozen 8.0 decisions are edited.

## Actual observed data & execution
- Frozen observed adjusted QQQ/TQQQ snapshot 2010-02-11 to 2026-10-09. 3,991 same-session cohort from 2010-11-26 to 2026-10-09.
- 100,000 USD initial wealth, no contributions, 98.5% risk-on invested, whole shares, 2bps trading fee + 10bps simulated slippage **each side**, close signal next-session OPEN (not real 09:31/09:32 execution).
- Frozen baseline **full-history ledger parity PASS**: 147 transactions and terminal equity match to better than a cent. Shared-window baseline has 127 transactions, CAGR 39.84%, MaxDD -49.08%.
- GitHub Actions reproducibility proof: https://github.com/badbuda/stocklense-public/actions/runs/42769855237
- Full JSON artifact: https://github.com/badbuda/stocklense-public/actions/runs/42769855237/artifacts/13741490932

## Factorial outcomes

| Layers ON TOP of StockLens | CAGR | MaxDD | trades | delta CAGR pp | MaxDD gain pp |
|---|---:|---:|---:|---:|---:|
| Frozen 8.0 | 39.84% | -49.08% | 127 | 0.00 | 0.00 |
| LRS | 35.08% | -54.10% | 69 | -4.76 | -5.03 |
| RSI | 37.23% | -48.15% | 281 | -2.61 | +0.93 |
| MACD | 28.70% | -43.22% | 1113 | -11.13 | +5.86 |
| TSI_EMA | 18.26% | -42.27% | 926 | -21.58 | +6.80 |
| LRS+RSI | 32.53% | -52.88% | 232 | -7.31 | -3.80 |
| LRS+MACD | 24.21% | -48.25% | 1068 | -15.63 | +0.83 |
| LRS+TSI_EMA | 14.05% | -43.15% | 917 | -25.78 | +5.93 |
| RSI+MACD | 27.60% | -43.85% | 1263 | -12.23 | +5.23 |
| RSI+TSI_EMA | 18.26% | -42.27% | 926 | -21.58 | +6.80 |
| MACD+TSI_EMA | 18.54% | -37.86% | 1250 | -21.29 | +11.21 |
| LRS+RSI+MACD | 23.15% | -47.89% | 1224 | -16.69 | +1.18 |
| LRS+RSI+TSI_EMA | 14.05% | -43.15% | 917 | -25.78 | +5.93 |
| LRS+MACD+TSI_EMA | 14.32% | -42.24% | 1243 | -25.52 | +6.84 |
| RSI+MACD+TSI_EMA | 18.54% | -37.86% | 1250 | -21.29 | +11.21 |
| **LRS+RSI+MACD+TSI_EMA** | **14.32%** | **-42.24%** | **1243** | **-25.52** | **+6.84** |

All comparisons on one historical snapshot (not pristine OOS). **After-tax returns not measured**.

## Additional stress results (independent comparison to corresponding baseline at same stress)
- RSI7 cap: lag0 with 10bps slippage `-2.61pp CAGR / +0.93pp MaxDD` but extra 1-session decision lag with 10bps: `-3.98pp CAGR / -2.99pp MaxDD` — not robust to delayed execution.
- LRS cap: negative CAGR *and* worse MaxDD in all four 0/1 additional lag × 10/20bps stress cases.
- MACD+TSI_EMA: MaxDD gain approx +9.17 to +11.21pp across four stress cases, BUT CAGR loss approx -21.29 to -26.46pp; high trading turnover.
- All four: with extra lag and 20bps slippage, CAGR delta -30.43pp and MaxDD delta -8.09pp; layering is **not** intrinsically protective.

## Conclusions and blocker list
1. This first pass does not identify any overlay combination that improves both CAGR and MaxDD versus frozen 8.0 on identical historical observations. No promotion.
2. The simple risk-only factorial may be too restrictive; significant long-term trend participation is lost. An alternative **staged**, low-turnover overlay is a separate *predeclared* future hypothesis, not something to tune against already viewed outcomes.
3. *Genuine Nasdaq market breadth* (% constituents above SMA50, bullish percentage index) still BLOCKED on point-in-time constituent data; not a member of the 16 tested layers. QQQ RSI is **not** breadth.
4. Full Autopilot 10%/20% partial profit-taking and 5%-7% stop execution require precise rule specification and intraday bars; the tested TSI+EMA8 is only a risk-signal proxy.
5. MACD-based interpretation isn't a reproduction of Masonson's trading rules; its chosen 2x cap is our experimental implementation.
6. No Israeli FX/FIFO capital gains tax, tax timing, cash carry, external contributions, genuine broker fills, untouched OOS, or future prospective evidence is claimed.
7. Preserve SL-58/59/60 as open research tasks. Frozen 8.0 unchanged, production untouched.

**Related:** [PR #171](https://github.com/badbuda/stocklense-public/pull/171) (this study), [PR #169](https://github.com/badbuda/stocklense-public/pull/169) (prior standalone screens), Jira SL-58, SL-59 and SL-60.

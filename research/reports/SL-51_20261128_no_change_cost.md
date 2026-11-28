# SL-51 unchanged-target rebalance study, 28 November 2026

Input snapshot 398d5993e458cb9deaa8ac64648a2d622e7f2318, docs/portal-history.json. Reproduce from project root with python -m research.no_change_cost_audit. Each period starts from $100,000 and zero shares. The prior completed signal drives the following daily adjusted open. Both Paper timestamps use that same open. Paper recomputes buy sizes after sales. Commissions are 2 bps and slippage is 10 bps each way. Tax, intraday spreads and actual broker fills are unobserved. Subperiods have been used in development.

| Period | Band (bp) | Orders | Unchanged-target trade days | CAGR | Max DD | Ending USD | Fees USD | Slippage USD |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2010-02-11 to 2026-11-27 | changes only | 153 | 0 | 35.79% | -49.05% | 17,016,796.66 | 54,751.67 | 273,758.81 |
| 2010-02-11 to 2026-11-27 | 25 | 821 | 382 | 36.01% | -48.79% | 17,501,634.59 | 59,145.72 | 295,729.13 |
| 2010-02-11 to 2026-11-27 | 50 | 519 | 197 | 36.07% | -48.77% | 17,626,443.83 | 58,801.00 | 294,005.50 |
| 2010-02-11 to 2026-11-27 | 100 | 270 | 60 | 35.99% | -48.97% | 17,449,312.46 | 56,853.06 | 284,265.79 |
| 2010-02-11 to 2026-11-27 | 200 | 187 | 17 | 36.00% | -49.10% | 17,466,373.11 | 56,419.76 | 282,099.32 |
| 2018-01-02 to 2022-12-30 | changes only | 61 | 0 | 27.68% | -48.59% | 338,555.03 | 1,188.30 | 5,941.76 |
| 2018-01-02 to 2022-12-30 | 25 | 347 | 159 | 28.28% | -48.74% | 346,557.00 | 1,285.84 | 6,429.45 |
| 2018-01-02 to 2022-12-30 | 50 | 220 | 84 | 28.31% | -48.75% | 346,999.28 | 1,271.33 | 6,356.90 |
| 2018-01-02 to 2022-12-30 | 100 | 123 | 31 | 28.08% | -48.92% | 343,869.25 | 1,237.26 | 6,186.58 |
| 2018-01-02 to 2022-12-30 | 200 | 81 | 10 | 28.07% | -48.83% | 343,816.40 | 1,219.02 | 6,095.33 |
| 2023-01-03 to 2026-11-27 | changes only | 19 | 0 | 49.14% | -45.33% | 475,165.07 | 1,121.24 | 5,606.10 |
| 2023-01-03 to 2026-11-27 | 25 | 159 | 86 | 49.52% | -45.14% | 479,849.09 | 1,193.26 | 5,966.21 |
| 2023-01-03 to 2026-11-27 | 50 | 84 | 37 | 49.55% | -45.18% | 480,233.23 | 1,178.81 | 5,893.99 |
| 2023-01-03 to 2026-11-27 | 100 | 34 | 8 | 49.38% | -45.25% | 478,161.77 | 1,137.69 | 5,688.36 |
| 2023-01-03 to 2026-11-27 | 200 | 25 | 3 | 49.49% | -45.27% | 479,480.99 | 1,138.73 | 5,693.57 |

The 50 bp filter adds 366 orders and 197 trade days at unchanged targets in 4,225 sessions. The gross-of-tax historical CAGR difference versus changes only is +0.285 percentage points. The worst drawdown improves by 0.282 points overall and worsens slightly in 2018–22. Retain the frozen rules pending tax, minute-price and independent data evidence. The old historical engine ends at $17,060,540.83 compared with $17,016,796.66 using Paper sizing on target changes only. Report these as separate execution contracts.

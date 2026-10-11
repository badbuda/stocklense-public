# StockLens SL9-013 — fixed observed GLD/TLT sleeve outcomes (2026-10-11)

## Verified evidence, scope
- Research PR: https://github.com/badbuda/stocklense-public/pull/58 (merged after Fast Guard success)
- CI: https://github.com/badbuda/stocklense-public/actions/runs/38109069344 — 499 tests passed, 8 artifacts retained (30 days).
- Exact results artifact: https://github.com/badbuda/stocklense-public/actions/runs/38109069344/artifacts/11691136955
- Source acquisition CI: https://github.com/badbuda/stocklense-public/actions/runs/38108795287; observed GLD and TLT 4,191 days each (2010-02-11 to 2026-10-09) plus 4,186 EFFR effective-date observations. EFFR never used in SL9-013 returns.
- GLD/TLT bar input SHA-256: `2f680455c1ba81eb2e859eb9520efb2c1139d2e2861ba715c697712004ee2210`.
- QQQ/TQQQ frozen source SHA-256: `bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129`.
- Frozen original 8.0 daily NAV reproduced exactly (within floating tolerance) against the existing independent whole-share engine across lag 0/1 and 10/20bps slippage cases.
- Every ETF price was a real observed Yahoo-adjusted daily OPEN/CLOSE proxy, **not a synthetic or 3x QQQ return**; however, the price-provider adjustments were not independently cross-audited and NBBO/venue fills were not obtained.

## Fixed portfolio construction and results
The prespecified comparison fixed all weights before observing the outcomes; no post-result tuning. 100k USD initial account, zero additions, physical whole-share ETF trades, 2bps fee per side + 10bps baseline slippage per side. Original StockLens target exposure preserved within its portfolio slice. Mixed portfolios also rebalance on level changes and first exchange session of each calendar year. Source signal dates precede trade dates.

| Portfolio (fixed, not optimized) | Full-period CAGR | MaxDD | Annual CAGR delta vs frozen | MaxDD improvement | Robustness continuation passes (of 4) |
|---|---:|---:|---:|---:|---:|
| **Frozen 8.0 100%** | **40.0263%** | **-49.0756%** | 0 pp | 0 pp | baseline |
| Frozen 85%, GLD 7.5%, TLT 7.5% | **36.5802%** | **-43.7717%** | **-3.4462 pp** | **+5.3039 pp** | **0/4** |
| Frozen 70%, GLD 15%, TLT 15% | **32.5180%** | **-40.1518%** | **-7.5084 pp** | **+8.9239 pp** | **0/4** |

The prespecified continuation rule requires **>=3pp MaxDD reduction AND <=1.5pp CAGR penalty** in *each* of lag0/1 × 10/20bps per-side slippage conditions. Both variants were REJECTED, despite large drawdown reductions.

## Correct interpretation and blockers
- There is a genuine historical *trade-off*, not improved risk-adjusted geometric growth under the chosen rule. 8.0 remains the best of these variants for maximizing historical CAGR. Some investors might choose lower volatility/MaxDD for lower expected growth, but that is a separate explicit utility decision, not an automatically promoted trading strategy.
- These dates are **reused historical data**, not new untouched OOS evidence. Selection bias and changes in structural regimes remain unresolved.
- Annual blended rebalancing changes turnover; no real broker commissions, FX conversion spread, execution timestamp quotes, tax drag or historical separate-account entitlements were verified.
- EFFR historical **effective dates** are not certified publication clock records and are **not** retail broker cash sweep yields. No claim of broker-rate-enhanced CAGR.
- Next true improvements require independently cross-verified prices and broker fills, actual cash entitlement/FX fees, and forward-looking paper sessions. Avoid endlessly tuning ETF weights on this reused sample.
- Original frozen StockLens 8.0 unchanged, no synthetic leveraged prices, no strategy promotion, no authorized capital deployment.

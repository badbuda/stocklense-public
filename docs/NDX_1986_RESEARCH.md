# StockLens 1986–present Nasdaq-100 index-price research (separate from ETF simulator)

**Status:** retroactive research only. The public portal's original **observed QQQ/TQQQ** simulation remains anchored to 2010-02-11 and is not modified. **This new panel must never be used as verified StockLens 8.0 performance, a live trading signal, or an Israeli tax return.**

## Why there are two simulations

- **1986–present (new panel):** FRED/Nasdaq `NASDAQ100` daily price-index closes. The index begins 1986-01-02. The frozen StockLens feature and level rules are applied **retroactively** using the previous **253 completed index closes**. The first possible modeled exposure is therefore in **1987**, not January 1986. The original frozen model initializes its state only in **September 2009**; this research model initializes after the 1986 warmup, so even its post-2009 signals may differ.
- **2010–present (unchanged):** actual observed QQQ and TQQQ adjusted daily ETF opens/closes with next-open modeled fills. This is the relevant tradable-instrument historical study, still not actual broker fills.

## Synthetic economics (not ETF historical data)

At each modeled day, previous-close signal determines one of the frozen exposure allocations: cash, 86.1875% 1× plus 12.3125% 3×, 49.25% each, or 98.5% 3×. The synthetic 1× sleeve earns the **price-index close-to-close** return. The synthetic 3× sleeve earns `3 * index_daily_return - annual_drag / 252` with a user-chosen drag assumption. The holdings drift between signal changes/deposits; at those points, the model rebalances and debits a user-chosen cost in bps of turnover. Cash return is assumed 0%. The benchmark is the Nasdaq-100 **price** index, not QQQ total return.

This model **does not** include: historical borrowing/financing rates, actual TQQQ daily tracking/expenses, dividends, withholding, split/market execution, real ETF OHLC before inception, broker fees, USD/ILS, tax lots, capital-gains taxes, or fund eligibility. It may be materially optimistic or pessimistic. The 3× drag and trading cost controls are assumptions, not calibrated historical estimates.

**Important:** If an index day falls more than ~33% after the assumed 3× drag, a synthetic 3× product would be wiped out. The simulator **stops** rather than inventing negative share prices or a recovery.

## Source and publishing

- [FRED NASDAQ100](https://fred.stlouisfed.org/series/NASDAQ100), original source Nasdaq, Inc.; FRED series starts 1986-01-02.
- `research/ndx1986_proxy.py` downloads CSV, checks date/price integrity, records SHA256 and produces `docs/ndx1986-research.json`. Missing values are excluded rather than filled.
- `.github/workflows/ndx-1986-research.yml` verifies the source, 253-day warmup and prior-close signal alignment before publishing the research-only feed.
- `docs/ndx1986-sim.mjs` loads that separate feed. Missing/unverified data -> **blocked**, without affecting the observed-ETF simulator.
- Check data license and redistribution permissions before any commercial/public redistribution beyond this research use; Nasdaq retains rights to its index series.

## Acceptance / future work

1. Independent source and date alignment audit, including 1987 crash and 2000–2002 drawdown.
2. Sensitivity to actual financing rate, daily ETF tracking, dividends and cash yield.
3. Separate 1987–2009 vs 2010–present analysis; **do not stitch synthetic and observed series into one claimed verified CAGR**.
4. If a 1986–present *after-tax* simulation is desired, require a separate historically valid tax/FX model and legal tax-wrapper eligibility; do not reuse the nominal 25% USD scenario as Israeli after-tax returns.
5. No changes to frozen 8.0, production, paper ledger, broker or AWS private endpoints.

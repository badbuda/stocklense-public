# StockLens — observed TQQQ only

**Effective 2026-10-08.** All new leveraged investment performance analysis must use actual observed TQQQ market prices, not daily QQQ returns multiplied by 3 or multiplied by the model exposure.

The only approved new public performance comparison is `research/tradable_tqqq_execution_comparison.json`, published as `docs/tradable_tqqq_execution_comparison.json`. Its QQQ benchmark must use observed QQQ prices for the *same dates and contribution schedule*. Do not splice synthetic pre-2010 periods into real-TQQQ results or fill gaps with simulated returns.

The frozen StockLens 8.0 decision logic and golden evidence remain unchanged for auditability; old Yahoo/LEAN approximations, including SL9-007 where a synthetic replay was used, are **archival diagnostics**, never current trading-performance proof and never inputs for a promoted challenger. Do not reuse old prospective evidence for a new real-ETF experiment; predeclare a distinct experiment and collect new forward rows.

Price source: observed TQQQ and QQQ adjusted OHLC. Historical fills modeled at next-session daily Open are **execution proxies only**; this is not an actual 09:31/09:32 execution or raw broker fill. Broker submission is disabled.

**Research work order:** 1) make observed-TQQQ source acquisition deterministic and fail closed, 2) validate session alignment, cash/whole shares, costs and delays, 3) compare against QQQ on the identical cohort, 4) test recent/past periods and loss concentration using observed ETF NAV, 5) only then evaluate separate predeclared challengers.

Policy source of truth: `research/OBSERVED_TQQQ_ONLY_POLICY.json`.

# SL9-021 — One fixed SPX implied-volatility term-structure mechanism
Date 2026-10-11, recorded **before experiment execution**. Frozen StockLens 8.0
remains unchanged, no live trading or auto promotion.

- Different from rejected lagged VIX spot-level guards in PR #62: measure the
  **slope between 30-day VIX and 93-day VIX3M**. Both are actual Cboe option-implied
  INDEX CLOSE levels, **not tradable futures contract prices**.
- Data: actual official Cboe `VIX_History.csv` and
  `VIX3M_History.csv` only, precisely aligned to the 4,191 completed XNYS
  frozen real-Q/T ETF sessions, no interpolation or synthesized missing indexes.
  Historical provider first-seen/intraday timing not independently certified.
- Rule: at modeled ETF OPEN t, use only completed session t-1 VIX/VIX3M.
  If VIX(t-1)/VIX3M(t-1)>=1.0, cap existing frozen leverage at 2x;
  otherwise do nothing. Keep 0x defense and all frozen signals untouched.
  First day missing earlier observation => no overlay.
- Only one challenger; not a grid of tuned curvature/threshold choices.
  Evaluate with real observed QQQ and TQQQ adjusted ETF daily OPEN/CLOSE,
  cash-constrained whole shares; 2bps modeled fee each trade side,
  10 and 20bps slippage; extra 0/1-session signal/index lag.
  Frozen baseline NAV must equal the established independent model
  day-by-day across all four matched cost/lag scenarios.
- **Predeclared historical continuation screen:** +3pp MaxDD improvement
  AND CAGR penalty <=1.5pp in every one of four lag/cost cases. Reused 2010–26
  is not clean untouched holdout. Not permission for capital even on pass.
- Source acquisition: fail closed to BLOCKED if VIX3M index is unavailable,
  invalid or missing any required previous-close observation. Never infer
  VIX futures term structure from these option-implied indices, or claim
  broker fills based on daily OPEN adjusted proxy.
- Fully offline unit tests for timing, missing dates, ratio and ledger parity.
  One bundled Fast Guard PR CI. Snapshot retained as expiring CI artifact
  rather than silently checking market-data blobs into the repository.

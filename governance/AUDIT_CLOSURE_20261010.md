# StockLens audit closure ledger — 2026-10-10

All listed engineering changes are **candidate code remediations**, not evidence of AWS runtime, independent market data, broker fills, or statistically significant alpha.

## Implemented in this batch (subject to Fast Guard and merge)

- **F-05':** `paper_rebalance_math.py` centralizes whole-share sizing, gap calculation and 50-bp NO_CHANGE band, consumed by `stocklens/paper.py` and `execution_cockpit.py`. Paper remains two-timestamp 09:31 SELL / 09:32 BUY; cockpit still has indicative last-published reference prices and explicitly **cannot** claim next-session order or fill parity.
- **F-18:** prospective minute-price journal uses `minute_open_prices` and `price_semantics=YAHOO_1MIN_BAR_OPEN_NOT_BID_ASK` for new sessions. Existing append-only `quotes` rows are **never rewritten**, including their historical SHA hash chain. Report exposes `bid_ask_quotes_observed=false`. A fake closed-XNYS day cannot be captured.
- **Accounting P0:** independent cash/whole-share inventory reconstruction from initial $100k capital and modeled trade receipts in `paper_portfolio_integrity.py`, including first session. Catches phantom cash/shares. Model-only NAV checking **does not independently prove vendor prices**, corporate-action completeness, executable spreads, or broker fills.
- **F-19:** upper SMA200 hysteresis 1.01 × SMA200 margin in basis points, warning at <10 bps. This is a data-source sensitivity diagnostic, not same-input LEAN parity. Dashboard explicitly labels shadow-only status and modeled minute-bar price scope.
- **F-09:** paper day-end close requires an official XNYS session with near-complete observed 1-minute bars and last bar within 2 minutes of official close (including early close days); cannot silently mark 100-minute data as full close.

## Still open (NOT safely closable by repository code alone)

- Confirm **deployed AWS Watchdog** first automatic schedule invocation / logs and errors; separately confirm deployed Lambda holiday policy and CloudFormation stability; do not confuse the initial missing-data alarm after creation with a real missed execution.
- Validate actual broker-independent 09:31/09:32 bid/ask, minute OHLC archive and a verified external quote source/SHA in durable independent storage; the existing Yahoo minute bar **OPEN** prices are not broker-executable fills.
- Validate LEAN original 7.24 code identity and private native input export, resolve pre-2010 and 2011 vendor adjustment drift; continue genuinely unseen fixed-baseline paired forward sessions (63 first operational review, 252 extended).
- Conduct risk-matched and beta-adjusted uncertainty-aware comparisons, selection bias/multiple-testing audit, broker sandbox lifecycle and explicit human approved loss budget before any live capital.

**Never** change frozen strategy on the basis of these diagnostic fixes. Keep automated live trading and broker orders disabled. One successful unit-test run is not live-system validation.

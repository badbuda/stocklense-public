# SL9-012 — Acquire actual GLD/TLT and EFFR effective dates (research only)

Date: 2026-10-11. Input acquisition, NOT a new return hypothesis or parameter search.

- Freeze existing StockLens 8.0 and observed-Q/T daily rows as immutable.
- Price: fetch via pinned yfinance adjusted DAILY open/close for fixed GLD/TLT symbols; do not forward fill gaps or invent prices, enforce exact 4,191 observed base sessions, positive finite quotes and calendar order; restrict to original frozen period.
- Archive only in CI short-retention artifact, not source files in public git; include source snapshot digest and explicit provenance limitations. A successful external download is not independent Yahoo adjustment audit or first-seen proof.
- EFFR: download from official NY Fed markets reference rates API. **The API effectiveDate is NOT the public first-seen availability timestamp.** Do NOT manufacture 9 AM exact historical receipt timestamps, retroactively add today’s vintage to historical disclosure, or equate EFFR to interest credit received from Excellence broker.
- Rate data is deliberately **not** passed automatically into the time-as-of cash simulator; require a separate, independently documented publication-time and broker-terms contract.
- No synthetic ETF price or returns, no new strategy promotion, no brokerage action. Partial/missing data => explicit BLOCKED and no fabricated profit comparison.
- After successful intake, an *independent later* fixed allocation study may compare original frozen 8.0 with predetermined initial 85/7.5/7.5 and 70/15/15 percent StockLens/GLD/TLT subaccounts, modeled ETF whole-share trades, realistic fees, no hidden rebalancing, full lag/cost robustness, new future sample before any decision. No optimization on reused 2010–2026 history.

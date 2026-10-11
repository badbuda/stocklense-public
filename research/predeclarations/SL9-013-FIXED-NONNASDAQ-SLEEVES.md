# SL9-013 — Prespecified REAL GLD/TLT diversification test

Date: 2026-10-11. Registered **before** first scoring run. Uses the already
repeatedly inspected 2010-02-11 to 2026-10-09 historical sample; NOT fresh OOS.

Data: SHA256 of actual GLD/TLT adjusted daily Yahoo prices from SL9-012 source
artifact run 38108795287: `2f680455c1ba81eb2e859eb9520efb2c1139d2e2861ba715c697712004ee2210`.
Real observed QQQ/TQQQ adjusted source snapshot:
`bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129`.
No synthetic leveraged ETF, stale source migration, ETF price interpolation
or invented broker 09:31 fills.

Three modes only, fixed before seeing outcomes:
- frozen 8.0 100%, no additional annual rebalancing
- frozen 8.0 85%, observed GLD 7.5%, observed TLT 7.5%
- frozen 8.0 70%, observed GLD 15%, observed TLT 15%.

At the base frozen leverage level change, or first XNYS session of each
calendar year (candidate modes only), rebalance physical ETF whole shares to
capital weights; stocklens sleeve invested fraction remains original 98.5%.
When frozen defense is 0, stocklens slice is in cash, but satellite persists.
Trades are priced at adjusted DAILY OPEN, not NBBO; 2bps fees/side, 10bps
baseline and 20bps adverse modeled slippage/side, 0/1 extra decision-session lag.
No deposits, taxes, currency spread or real broker observed executions.

Compare all matched lag/cost cases to frozen. Research continuation ONLY if
MaxDD improves at least 3 percentage points AND annual CAGR falls by no more
than 1.5 pp in ALL four scenarios. No retune weights after outcomes, no
promotion regardless of apparent score. Include historical periods 2010-17,
2018-22 and 2023-26 as reused diagnostic eras; no significance claimed.
Holdout/paper validation, input provider adjustment audit and venue execution
needed before any deployment.

Single fixed CI batch; downloaded source archive is from verified SL9-012
CI #38108795287, NOT newly synthesized or silently sourced. Failure to
download this exact archive MUST fail study rather than fabricate data.

# SL9-019 — directly test Claude's inverse-variance vs downside-semivariance drag mechanisms
2026-10-11. Written prior to viewing outcomes. No strategy promotion or live broker.

Observations: original immutable 4,191 real QQQ/TQQQ adjusted DAILY bars,
2010-02-11 to 2026-10-09, price fingerprint
`bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129`.
All decisions use frozen 8.0 levels, min(frozen,cap), zero stays zero, *never*
increase frozen risk. No fabricated TQQQ or QLD prices.

Two new **fixed** families:
- `inverse_variance20`: cap `clip((0.60/sigma20)^2,1,3)`,
  where sigma20 is annualized stdev of previous 20 completed QQQ daily
  log close-to-close returns.
- `downside_semivariance20`: cap `clip(0.60 / sqrt(2*252*mean(min(r,0)^2)),1,3)`.
  Symmetry-normalized downside volatility, annualized, from previous 20
  completed QQQ closes. Distinct from realized total variance; no volume
  proxy or future news.
Common `0.005` max notional weight-gap no-trade band for candidate modes
to reduce micro-turnover. This band is taken unchanged from earlier Vol60
and *is not* separately optimized in this research. Exact original 8.0
whole-share NAV parity mandatory in four lag/cost cases.
Real physical ETF holdings, $100k no deposits, 2bps commission/side,
10/20bps slippage/side, lag 0/1 extra completed session only, modeled
daily OPEN execution not 09:31 broker NBBO.
Continuation screen all four stress cases: >=3.0 percentage points MaxDD
improvement and no more than 1.5pp CAGR reduction. Report all failures.
2010–2026 already repeatedly studied, NO clean OOS or robust alpha claim.
Do not inspect outcome and retune sigma window or 0.60.

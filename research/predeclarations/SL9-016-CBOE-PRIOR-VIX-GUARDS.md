# SL9-016 — two fixed prior-day Cboe VIX risk layers on real QQQ/TQQQ

Date: 2026-10-11, preregistered BEFORE viewing backtest outputs.

**Distinct from the rejected EWMA realized volatility rules:** VIX is an
SPX-option-based forward-looking implied volatility index, not computed from
realized QQQ returns. Official Cboe daily close CSV:
https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv
Official historical data guide: https://www.cboe.com/tradable-products/vix/vix-historical-data

Base historical source: 4,191 real observed Yahoo-adjusted QQQ and TQQQ
daily OPEN/CLOSE bars and frozen original 8.0 prior-completed-close decision
ledger (SHA bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129).
Never synthetic TQQQ, no true broker 09:31 quotes and no independently verified
historical VIX vendor first-seen or revisions.

Only THREE modes, fixed ex ante:
- frozen: exact 8.0 leverage in {cash,1.25x,2x,3x}
- `vix_high_tier`: after yesterday's VIX close reaches >=30, cap at 2x;
  at >=40, cap at 1.25x. Never increase leverage over frozen.
- `vix_five_session_shock`: at yesterday's VIX >=40 cap 1.25x;
  at VIX >=25 AND its jump >=5 index points over the 5 completed
  exchange sessions preceding the prior close, cap 2x.
  Otherwise identical to frozen.

Each modeled OPEN i sees at most VIX close i-1 (or i-2 for an additional
full decision lag); never same-day VIX value. No interpolation or forward-fill:
the experiment fails if even one prior exchange session VIX close is missing.
No threshold grid, fitting, post-result retuning, crisis-date anchor selection,
or optional cherry-picked benchmark period.

Trade exact observed adjusted next OPEN physical QQQ/TQQQ shares, 2bps fee
and 10bps (20bps adverse) per-side modeled slip, initial USD100k and zero
monthly contributions. Frozen NAV must replicate existing simulator day by day
across lag0/1 x 10/20bps. Report CAGR, MaxDD, all four matched costs/lags
and the three REUSED time splits already in StockLens report (2010-17,
2018-22, 2023-26). Not a pristine holdout.

Research continuation only if BOTH **MaxDD improves >=3.0 percentage points**
and **CAGR deterioration <=1.5pp** in ALL four matched cost/lag scenarios.
Pass does NOT imply a tradable result; it merely permits later independent
market quotes/vintage and prospective paper validation. No auto model promotion,
no broker transactions and immutable StockLens 8.0.

The downloadable historical CSV itself is a *modern snapshot* of old VIX
closes. That does NOT prove the earliest actual VIX vendor publication time.
Use previous completed session only as a conservative timing assumption,
never as independently authenticated vendor PIT. No event-news alpha claim.

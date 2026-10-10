# SL9-009: Five fixed, observed-ETF challenger experiments (2026-10-11)

No modification of StockLens 8.0, no real trading, no automatic model promotion.
The entire 2010-02-11 to 2026-10-09 Yahoo-adjusted observed QQQ/TQQQ
historical sample has already been inspected; it is NOT pristine out-of-sample.

## Predeclared hypotheses, before seeing this batch's outcomes

1. cap_2x: never exceed 2.0x invested leverage when frozen would be higher.
2. cap_2_5x: never exceed 2.5x; a Kelly-adjacent structural risk cap, not a calculated optimum.
3. staged_up_3: increases between non-zero exposure levels staged over 3 opens;
   decreases and zero-defense immediately honored.
4. staged_both_3: up/down changes between non-zero levels over 3 opens;
   zero-defense immediate. This can catastrophically delay risk reduction.
5. ewma5_shock: QQQ 5-day EWMA squared log returns from previous CLOSES,
   cap min(3,max(1,.60/annualized_vol)), plus cap 1.25x after prior
   daily QQQ return <= -4%, or 3-session return <= -8%.
   No same-day volatility or same-day drop can trigger at same-day opening.

Use original frozen decisions for every mode, with genuine observed
Yahoo QQQ/TQQQ adjusted DAILY OPEN/CLOSE and whole-share ETF ledger.
Same fee of 2bps/side, hypothetical slippage 10 or 20bps/side.
Stress additional frozen execution delay 0/1 session, compared against
a matching delayed frozen reference in the same stress settings.
2 delays x 2 costs x 6 modes = 24 modeled paths. Reuse 2010-17,
2018-22 and 2023-26 only for descriptive continuity; do not select
hyperparameters or recalculate initial NAV separately in each era.
Before any new result, verify all frozen NAVs against old audited
next-adjusted-open baseline with tolerance at most 1e-5 USD.

Historical continuation gate: >=3 percentage points improvement in
MaxDD AND loss in CAGR <=1.5 percentage points, in ALL four
delay/cost stress settings. No automatic promotion even if this passes.
Each of five comparisons counts against multiplicity; do not retune
thresholds using these same outcomes.

## Cash sweep scenarios separate from market-timing variants

Hold 0%, 2%, and 4% *fixed ANNUAL interest* on actual prior-period
simulated cash, accrued over elapsed calendar days before next open.
These scenarios do NOT represent historic daily T-bill rates, the actual
broker sweep yield, borrow rates, tax, FX, or real executable products.
A fixed rate across 2010–2026 is knowingly counterfactual. Treat
as accounting sensitivity ONLY and seek historical PIT rate series plus
broker sweep contract before a production claim.

## News sample separate from historical alpha

Manually checked official historical source URLs and release-clock
facts are cataloged in research/samples/official_release_2022_not_pit.json:
Jan-26-2022 FOMC statement at 14:00 EST (Federal Reserve), and
Sep-13-2022 archived CPI report (BLS). Both explicitly FAIL
point-in-time first-seen/vendor delivery proof and are NOT fed into
news-event research or risk orders. Event calendars are not surprise
outcomes and press-release times are not independently proven
vendor-first-seen trade availability. These are archival provenance
SAMPLES, not a backtested positive result. The existing SL9-008
news research remains data-blocked. No article text republication.

Do not expand this same grid after looking at winners. If thresholds
fail, log negative results, then prioritize independently timestamped
vendor news, cross-market transfer, actual broker fills and prospective
shadow data instead of endless mining of the repeatedly observed period.

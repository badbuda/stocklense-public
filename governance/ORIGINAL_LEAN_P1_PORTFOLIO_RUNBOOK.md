# StockLens 7.24 — P1 portfolio path and P0 precision research (2026-10-10)

## Why a new portfolio observer is necessary

The original frozen 7.24 LEAN backtest had 3,774 matched daily P0 decisions, 345 simulated orders and 301 closed-trade records matched except generated UUIDs. All original SL724 Leverage/NAV/Drawdown series were unchanged in the P0 rerun. Those outputs prove neither daily cash/position accounting nor broker execution realism.

**7.24 and 8.0 are not identical portfolio accounting models.** Original 7.24 used QQQ/QLD before TQQQ eligibility and QQQ/TQQQ afterward; original orders sell at NY 09:31 and buy at 09:32, with 2bps fees and VolumeShareSlippageModel(.10,.10), not a uniform next-daily-OPEN execution assumption. It started at $100,000 and added **179 monthly $3,500 deposits** from Oct 2009 through Aug 2024 for total invested capital $726,500. It tracks contribution-neutral chart NAV by dividing actual equity by algorithmic units. Original QC CAGR 47.373%, end equity $34,817,008.35 and QC reported MaxDD 48.600% must **not** be equated with 2010–2026 noncontributing observed-ETF 8.0 daily-open CAGR ~40.03%. Data windows and denominators differ.

## Private observer prepared — original strategy code unchanged

Private Library artifact: /SL724_QuantConnect_P1_Portfolio_Observer_PRIVATE.zip

Input is original frozen 7.24 Python source SHA256 88fb83825542b5a7ac4b91dcc92af0840c293f31d6d324d45b865ef4dcfdd885. A copied main.py has seven *additional plot calls only* in capture_close, after the original SL724 three plot calls. Removing them recreates the source byte for byte. No decisions, holdings, orders, cashflows, commissions, or brokerage controls are changed.

New chart SL724_P1_PORTFOLIO must contain all **3,774 original SL724 closing timestamps**, without omissions, in each of equity, cash, qqq_quantity, qld_quantity, tqqq_quantity, units, contributed. The P1 observer MAY additionally emit a **3,775th point on 2024-08-30**, the unique next XNYS trading day. The original SL724 chart stops on **2024-08-29**, whereas the original QC run is configured through **2024-08-31** and includes August 30 trading. The importer records any authentic trailing observation separately; it refuses misdated or multiple extra points and does not silently extend the locked 3,774-day original chart. holdings_value is inferred as equity minus cash; it is not independently observed. Plot transport may quantize native values, so parity claims must report explicit numerical tolerances and not imply native bit-level precision.

To collect it: launch a NEW **private** QuantConnect project with main.py from that private ZIP, keeping the original and previously completed P0 observer project unchanged, run original dates and download the full Results JSON. Do not upload the original source or raw JSON to public GitHub.

After the private P1 rerun, use:

    python qc_private_lean_portfolio_acquisition.py --original '/private/Determined Red Orange Duck.json' --diagnostic '/private/P1 portfolio observer Results.json' --out-private-csv research/local/qc_lean_p1_daily_portfolio_PRIVATE.csv --audit-private-json research/local/qc_lean_p1_daily_portfolio_audit_PRIVATE.json

The importer locks the actual original chart via the preexisting SHA-pinned extraction, confirms 345 orders and all native original economic/chart invariants still match, checks every P1 timestamp equals the corresponding original original-LEAN chart timestamp, rejects missing or extra observations, validates contributed 100,000+179*3,500=726,500, cash and quantity plausibility, native chart NAV against equity/units, and original ending account equity/holdings. It does not compare to a fabricated Python NAV path and never upgrades capital readiness.

## P0 chart rounding conditional robustness

The complete private aligned feature CSV, sha256 e2dc51312a23948c8cf270c80ceffa837269f3f713912852c7d7fc42fbde98de, was independently examined over all 3,774 original decisions. Under ASSUMED maximum absolute plot perturbation 0.0001 for close/SMA50/SMA200 and 0.000001 for vol20/mom12, all decision branch inequalities stay on the same side of their thresholds. Zero of the 3,774 decisions could flip under the specified error envelope.

| Native decision inequality | Minimum residual margin after assumed error |
|---|---:|
| SMA200 hysteresis close comparison | 0.0117767 |
| SMA50 versus SMA200 | 0.0033000 |
| 12-month momentum zero crossing | 0.0001304686 |
| Realized volatility thresholds | 0.0000253 |

**This is conditional on the chosen assumed error bounds, NOT an independent measurement or proof of the QC chart encoder precision or original unrounded feature bits.** The private aggregate, without raw daily features, was saved in Library under StockLens_QC_P0_chart_precision_3774_PRIVATE.json.

## Open scientific gates

- Native P1 portfolio chart backtest must still run in private QuantConnect; seven new series have not yet been observed.
- Original 7.24 compiled build-source identity, native unrounded indicator price inputs, and exact independent market data adjustments remain unattested.
- LEAN simulated fill/quote data are NOT timestamped independent exchange NBBO or actual broker fills.
- Native P1 observed portfolio chart versus independently reconstructed Python same-start portfolio path requires identical inputs, three ETF tickers, complete monthly contributions, corporate actions, and original 09:31/09:32 order timing. P1 chart alone does not establish this.
- Frozen StockLens 8.0 remains untouched and real capital execution blocked; continue honest forward matched Paper.

**Critical terminal-accounting guard:** original native End Equity ($34,817,008.35) and runtime Holdings may refer to **2024-08-30** rather than last custom SL724 plot 2024-08-29. Comparing those endpoint statistics against a P1 *Aug 29* chart value as if they had the same date would yield a false error or false certification. If P1 contains only 3,774 original-aligned points, the endpoint is explicitly marked `BLOCKED_CHART_END_BEFORE_RUN_END`; when it contains the exact independently calendar-checked Aug 30 point, terminal equity/holdings may be verified against the proper same-day statistics. In either case the original 3,774 dates remain checked and output separately. The private bundle README was corrected and the same Library file overwritten in place.

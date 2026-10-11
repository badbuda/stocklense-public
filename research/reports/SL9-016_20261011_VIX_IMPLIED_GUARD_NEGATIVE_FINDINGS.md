# SL9-016 — observed Cboe VIX implied-risk fixed challenger findings

Date: 2026-10-11. RESEARCH ONLY. Frozen StockLens 8.0 unchanged. No synthetic TQQQ, real brokerage trades, or algorithm promotion.

## Reproducible provenance and CI
- PR #62 merged: https://github.com/badbuda/stocklense-public/pull/62
- Green full Fast Guard CI: https://github.com/badbuda/stocklense-public/actions/runs/38110935489 — **524 tests passed**, 8 archived artifacts.
- VIX raw source (as observed *today*, not independently certified original historical publication vintages): Cboe official `https://cdn-api.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv`, linked from `https://www.cboe.com/tradable-products/vix/vix-historical-data`. Market days fully aligned: 4,190 prior session closes for 4,191 modeled trading sessions, Feb 11, 2010–Oct 9, 2026. VIX series snapshot digest over selected indexed data: `449bb5dad2729db20525e85876835d97a62f1958d360b8afa0679b7131c6bf74`.
- Real observed Yahoo-adjusted QQQ and **actual TQQQ** daily OPEN/CLOSE, market snapshot SHA `bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129`. No synthetic TQQQ approximation.
- Original frozen 8.0 whole-share NAV parity passed **all** 0/1 additional session lag × 10/20bp modeled per-side slippage cases, with 2bps fee each side.
- Neither contemporary historical Cboe first-seen timestamp/retroactive revisions nor exact 09:31 broker NBBO execution observed; daily OPEN is a modeled proxy. Historical sample reused multiple times, NOT clean held out.

## Fixed before observing any outcomes (not a parameter search)
Both methods apply strictly to frozen 8.0's existing leverage target. The VIX observation must be the **previous completed market day's close**, never current-session close, and never after the frozen 8.0 decision. No missing-day padding.

1. `vix_high_tier`: VIX>=30 caps target leverage 2x; VIX>=40 caps 1.25x. Intervention sessions: 62.
2. `vix_five_session_shock`: VIX>=40 caps 1.25x; else VIX>=25 plus +5 points in previous five completed NYSE sessions caps 2x. Intervention sessions: 59.

| Research mode | 2010–2026 CAGR | MaxDD | CAGR loss vs frozen | MaxDD improvement vs frozen | 0/1 lag ×10/20bp screen |
|---|---:|---:|---:|---:|---:|
| **Frozen StockLens 8.0** | **40.0263%** | **−49.0756%** | — | — | Reference |
| Fixed VIX 30/40 tiers | **37.2594%** | **−54.9315%** | **−2.7669 pp** | **−5.8559 pp** (WORSE) | **0/4** |
| Fixed five-session VIX jump | **38.4368%** | **−49.1476%** | **−1.5895 pp** | **−0.0719 pp** (WORSE) | **0/4** |

Threshold: minimum +3.0pp MaxDD improvement and no more than 1.5pp CAGR deterioration in ALL four matched lag and slippage scenarios to justify *further research*, never automatic promotion. **Both fail**. These failures do not prove that no implied-risk approach can ever work; no reasonable license to tweak thresholds repeatedly on the same 2010–2026 sample.

## Interpretation
VIX provides genuinely **different information** (SPX option-implied market expectations) from realized QQQ volatility. Nevertheless, these predefined delayed close-trigger rules lost material compounded growth and did not alleviate worst historical drawdown under actual observed ETF proxy implementation. Faster implied risk alone cannot resolve severe overnight gap and whipsaw timing when trades occur only at the modeled following OPEN.

## Remaining evidence priorities (separate from VIX parameter grid)
1. Actual broker 09:31/09:32 quotes and execution fills/partial fill data, FX spreads, cash-sweep contracts and taxes — not yet sourced.
2. Corporate HY credit risk / government yield curve independent published historical *vintages* (FRED/ALFRED) rather than retroactively amended end-of-day data, plus conservative availability latency, before any next fixed family. Note FRED ICE BofA HY OAS publicly has a **3-year only** history under new restriction from April 2026; do not pretend it covers 2010–2026.
3. True VIX term structure forward prices, not daily spot VIX, requires historical underlying tradable futures *with real quotes*.
4. Genuine SEC/GDELT as-of archive receipts, FOMC/CPI pre-release consensus and past-only causal control matching; currently zero independently verified historical first-seen news events.
5. Prospective frozen Paper trial with immutable daily signal, prices and timeliness audit; avoid more retrospective pre-selection.

All findings historical, descriptive, non-actionable for trading; StockLens 8.0 immutable; no capital deployment.

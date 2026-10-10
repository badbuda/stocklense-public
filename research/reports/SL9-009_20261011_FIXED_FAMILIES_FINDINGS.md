# StockLens SL9-009 — results, five-family risk overlay falsification and idea triage
Completed 2026-10-11, verified PR #54 and Fast Guard #74.

## Evidence and precise boundary

- Merged PR: https://github.com/badbuda/stocklense-public/pull/54
- Green CI: https://github.com/badbuda/stocklense-public/actions/runs/38086059234
- Full official CI JSON/Markdown (30-day retention): https://github.com/badbuda/stocklense-public/actions/runs/38086059234/artifacts/11682327498
- 470 unit/regression tests passed; frozen baseline day-by-day NAV identical to prior audited local whole-share observed ETF OPEN proxy.
- Observed Yahoo-adjusted QQQ+TQQQ (NOT synthetically levered QQQ), 4,191 sessions from Feb 11, 2010 to Oct 9, 2026.
- Hypothetical DAILY OPEN orders in whole ETF shares, 2bps fee per side, 10bps base slippage per side. True intraday bid/ask, 09:31 fills, real brokerage statement and independent later sample remain unavailable.

| Frozen / preregistered challenger | CAGR | MaxDD | annual CAGR delta pp | MaxDD improvement pp | gate passed (of 4) |
|---|---:|---:|---:|---:|---:|
| frozen StockLens 8.0 | 40.03% | -49.08% | 0 | 0 | reference |
| cap_2x | 30.54% | -45.09% | -9.49 | +3.99 | 0 |
| cap_2_5x | 35.44% | -46.67% | -4.58 | +2.41 | 0 |
| staged_up_3 | 39.28% | -49.25% | -0.75 | -0.18 | 0 |
| staged_both_3 | 39.02% | -51.07% | -1.01 | -1.99 | 0 |
| ewma5_shock | 37.43% | -45.93% | -2.60 | +3.15 | 0 |

**No winner.** Five of five challenger hypotheses failed preregistered threshold: MaxDD must improve by at least 3pp AND CAGR penalty must be <=1.5pp in each of four lag0/1 × slippage10/20bp conditions. Freeze rejects; no posthoc retune, no model promotion, no capital authorization.

## Cash interest sensitivity (not realized historical rate path)

Applied constant annual 0%, 2%, 4% for *all 2010–26* to actual modeled prior cash balances, credited before next trading open over elapsed days.

| Hypothetical constant annual cash rate | Portfolio CAGR | Incremental CAGR |
|---|---:|---:|
| 0% | 40.0263% | 0pp |
| 2% | 40.2298% | +0.2035pp |
| 4% | 40.4298% | +0.4035pp |

These are counterfactual accounting estimates, NOT a backtest with period-correct Treasury yields, not broker cash sweep, not after-tax or after-currency-exchange fees.

## News pilot and contemporaneous source problem

- Implemented in PR #53: genuine PIT fail-closed event timestamps, conservative GDELT/SEC provider adapters, official provider registry, protected intake, next eligible NYSE session descriptive event-study and anti-leakage tests.
- CI result: historical event records=0, PIT eligible events=0, status BLOCKED_NO_GENUINE_TIMESTAMPED_HISTORICAL_EVENT_COHORT.
- Manually sampled Federal Reserve FOMC release from 2022-01-26 at 14:00 EST and BLS CPI report from 2022-09-13 (see research/samples/official_release_2022_not_pit.json). Original official release page dates are not archival proof of historical vendor first-seen delivery or point-in-time consensus.
- No news-improved historical CAGR asserted, no current LLM hindsight applied to old events, no extrapolation from two sample events.

## Complete idea triage, not unbounded research

### Closed or directly tested

- **Simple leverage ceilings/Kelly-adjacent**: both 2x and 2.5x tested in SL9-009; both rejected under risk-adjusted screen. Historical mu/sigma² optimal Kelly cannot be inferred robustly from future realized moments.
- **Stagger entry/change execution**: 3-session up-only and symmetric nonzero staging tested; neither reduced MaxDD enough, symmetric materially worse.
- **Fast EWMA risk and crash response**: 5-day EWMA + 4% one-day / 8% three-day shock tested; MaxDD improvement 3.15pp bought at CAGR -2.60pp, rejected.
- **Continuous volatility targeting / ramped reentry**: already tested SL9 Vol60 on actual observed ETF OPEN proxy (PR prior to #54); failed all robustness gates, do not reopen thresholds.
- **Simple ML risk layer**: PR #52 (Ridge walk-forward up/down/both and simple momentum control), none passed; R² below training-mean prediction benchmark in each reused era, no new neural net hyperparameter mining.
- **Cash yield**: three deterministic constant-rate scenario accountings completed; actual historical yields and broker conditions remain unresolved.
- **Preannounced FOMC/CPI calendar events**: first archival source provenance sample completed, descriptive only, with no verified PIT-delivered outcome/surprise cohort.

### Independent inputs required — do not fabricate full backtests

- **Soft thresholds / sigmoid around boundaries**: not identical to staging, requires predeclared interpolation rule against *prior close* and whole-share proxy; earlier transition-plateau diagnostics exist. High multiple-comparison risk; defer until new external sample.
- **Diversification outside Nasdaq / gold / Treasury ETF / trend sleeves**: require observed PIT prices for distinct instruments, correct inception coverage, comparable portfolio contribution and tax accounting; not StockLens signal change.
- **Actual broker friction / FX spread / changing contribution schedule**: obtain Excellence Trade commission, minimum trade, FX fees, cash eligibility and deposit schedule; a model without the contract is not proof.
- **Rate-aware leverage / actual Treasury defense asset / FRED credit spreads, curve**: point-in-time rate/vintage, exact release availability and actual ETF trading/funding costs missing. ALFRED vintages alone do not establish intraday timestamps.
- **QLD vs blended QQQ/TQQQ, sector sleeves UPRO/SOXL, multi-window trend**: optional distinct research once observed real prices and split-adjusted execution/inception verified; do not claim 1987 observed TQQQ (not available).
- **Market breadth**: historical constituent PIT/delisting coverage missing; modern constituents are survivorship contaminated.
- **Put hedges/MNQ futures**: historical option chains, implied vol and quote availability, contract roll, margin and liquidation/margin-call risk missing. Not comparable to an imaginary zero-cost protective payoff.
- **Corporate M&A/earnings, geopolitical news, elections**: SEC filing acceptance is not a verified first market-observed headline; historical ticker mappings and independently archived provider delivery needed.
- **Valuation CAPE, seasonal rules, shorting SQQQ and optimizer sweeps**: lowest priority; not a reason to proliferate additional after-the-fact experiments.

## Research priorities after negative results

1. Point-in-time archived provider delivery for GDELT + SEC, plus actual pre-release consensus vintage for CPI/FOMC; start with descriptive study before any predictive layer.
2. Independent 09:31/09:32 actual NBBO/venue fill validation; fees, slippage, gap and adverse selection measured rather than assumed.
3. Actual broker cash sweep/interest rates, risk-free and funding costs by historical date; avoid fixed-4%-forever economic inference.
4. Locked prospective (63 then 252 complete sessions) observed ETF Paper and QQQ comparison; historical 2010–26 source has already been reused.
5. Portfolio-level non-Nasdaq diversification as separate sleeve (not a change to frozen 8.0).

**Final status:** Frozen 8.0 unchanged. Historical risk overlay contenders rejected. News alpha blocked by missing genuine PIT journal. Capital deployment prohibited.

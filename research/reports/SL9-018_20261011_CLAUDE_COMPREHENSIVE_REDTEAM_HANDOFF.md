# StockLens 8.0 / Claude Independent Red-Team Handoff
**Evidence cut-off: 11 October 2026 — research-only; frozen strategy preserved.**

**To Claude:** Review the actual StockLens evidence below as an independent adversarial quant and systems reviewer. Challenge arithmetic, look-ahead, causal information timing, realistic execution, data provenance and multiple-testing. Do **not** optimize dozens of parameters against the reused sample or treat CI green as economic alpha. Suggest at most three non-redundant, preregistrable mechanisms with explicit data prerequisites, falsification tests and practical cash/execution costs. Do not authorize capital, connect broker order submission, or promote a model.

## Addendum — verified after the original handoff, 11 October 2026

**PR #65:** [real-Q/T inverse-variance and downside-semivariance trial](https://github.com/badbuda/stocklense-public/pull/65) **merged**, [CI #38112459649](https://github.com/badbuda/stocklense-public/actions/runs/38112459649) **538 pytest passed**. Fixed rules on actual observed QQQ/TQQQ daily adjusted opens, historical reused 4,191 sessions; no synthetic TQQQ, no real broker fill or fresh holdout. Results from actual CI job log:

| Preregistered mode | CAGR | MaxDD | ΔCAGR vs 8.0 | MaxDD improvement | Modeled trades | Passing stress gates |
|---|---:|---:|---:|---:|---:|---:|
| Frozen 8.0 | 40.0263% | −49.0756% | — | — | 147 in earlier baseline | baseline |
| Inverse variance, prior 20 sessions | **39.8642%** | **−49.0756%** | **−0.1621 pp** | **0.0000 pp** | **177** | **0/4** |
| Downside semivariance, prior 20 sessions | **37.3498%** | **−47.7857%** | **−2.6765 pp** | **+1.2899 pp** | **1,010** | **0/4** |

Thus the earlier handoff row calling *inverse variance* directly "UNTESTED" is superseded for these two fixed implementations only. **Neither passes**. Inverse-variance risk gating remains not a proven general impossibility, and Kelly / macro/news variants are not validated. **Do not retune variance lookback or fraction on the reused sample to chase a winner.**

**PR #63** (forward evidence mismatch visibility) and **PR #64** (maturity requires fingerprint consistency) are now **both merged** with their terminal green CI [#38111961760](https://github.com/badbuda/stocklense-public/actions/runs/38111961760) **528 passed** and [#38112178833](https://github.com/badbuda/stocklense-public/actions/runs/38112178833) **533 passed** respectively. The SL9-007 queue/registered evidence digest mismatch remains **unreconciled**, while its experiment-definition digest matches; implementation prevents falsely labelling drifted prospective data "CURRENT"/mature. Two historical simulated paper ledger sessions remain insufficient to establish live execution quality. The initial failed CI for #63 was followed by a genuine green run; it is **not** currently an open failing PR.

### Claude: questions that matter next
1. Verify *independently* whether fingerprint drift is a benign refresh or material replacement: immutable producer commits, original daily market-data bytes, acquisition times, and each archive SHA; do not reset the registration. Give an explicit forensic proof chain or say **UNRESOLVED**.
2. Audit actual stocklens8 broker-executable Open/VWAP assumptions with observed 09:31/09:32 NBBO and bid/ask, fee/margin/FX and dividend/split accounting. Current one-minute Yahoo **bar OPEN** sample is neither bid/ask nor an actual broker fill.
3. Choose at most **three** new orthogonal, ex-ante plausible hypotheses from remaining BLOCKED/UNTESTED sectors (e.g., independently vintage-certified credit/yield/futures term structure, survivorship-safe breadth, genuine PIT corporate/macro surprises). For each demand archival source availability first, no implied event first-seen, exact lag/cost, self-attestation rejection, frozen-8 match, untouched forward evidence. Do not propose more 20-day RV threshold tweaks after failed #65.

---

## SL9-020 verified forward provenance audit — important correction (11 Oct 2026)

**[PR #66](https://github.com/badbuda/stocklense-public/pull/66) was merged after [green CI #38115590992](https://github.com/badbuda/stocklense-public/actions/runs/38115590992): 545 tests passed, research artifact archived.** Do not characterize this as a new strategy return result. It is an independent-evidence readiness audit, and the headline is **0 independently qualified forward trading rows**.

- Registered SL9-007 rows preserved, total **10**; **8** already appear together in the first accessible Git snapshot, with no individually certified original observation times.
- Of all ten rows, **3 have plausible Git author-time windows** between the session close and next open, and **7 do not**; *even the three are not proven real-time captures*. Git author timestamps are client-supplied and are not independent server receipt times.
- Original `research_data_adapter.py` and `research_upshift_confirmation.py` compute **QQQ daily close-to-close return × selected leverage**, NOT real observed TQQQ portfolio returns and NOT broker fills. This is appropriate as a limited research proxy but insufficient to qualify as prospective observed leveraged-ETF performance.
- Evidence fingerprint drift persists; the experiment definition fingerprint is stable. The earlier #63/#64 fail-closed flags must stay in place. Do not reset fingerprints or backfill.
- Different from the *two* original frozen portfolio Paper ledger entries (Oct 8/9) and the single Oct 9 prospective Yahoo one-minute BAR OPEN journal, these ten research rows are not independent execution receipts.
- Evidence artifact and explicit failure reason: [SL9-020 Git first-appearance audit](https://github.com/badbuda/stocklense-public/blob/main/research/reports/SL9-020_20261011_GIT_FIRST_APPEARANCE.md), output `research/results/sl9_020_forward_git_audit.json` archived in CI. The audit specifically states `BLOCKED_INDEPENDENT_FORWARD_CAPTURE_NOT_PROVEN`.

**Claude red-team ask:** propose an exact append-only design that atomically binds a prior-close signal digest, next-open real observed TQQQ price/quote evidence, captured-at SERVER timestamp, provider receipt, market calendar, full fees and post-trade NAV. Distinguish one-minute OHLC opens from executable NBBO, real broker fills, and revised price feeds. Preregister next 63 XNYS sessions with a 252-session checkpoint; do not mine the existing 2010–2026 proxy sample.

---

## Executive finding

**No new candidate has met the preregistered continuation requirements. StockLens 8.0 remains the reference and the highest historical-CAGR result among the selected tested alternative families.** This is not proof of market-beating *selection-corrected* alpha, broker-realizable returns or future performance.

- Market period: **2010-02-11 through 2026-10-09**, **4,191 XNYS sessions**, actual observed Yahoo adjusted QQQ and **real TQQQ** daily open/close; **NO synthetic TQQQ** in the new ETF comparisons. Price source fingerprint `bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129`.
- Fixed historical whole-share book, $100k initial, no contributions for risk studies, modeled open fills, 2bps fees/side and 10bps base or 20bps adverse slippage/side, 0/1 additional session lag where specified; selected studies also exercise 2-session lag/30bps. No venue NBBO quotes, market impact, tax, USD/ILS conversion or actual broker execution.
- **Frozen 8.0: CAGR 40.0263%, MaxDD -49.0756%; matched QQQ CAGR about 19.7510%** in the historical source. Max single modeled daily loss **-15.258%** on 2020-09-03. These are hypothetical.
- General risk limitation: the 2010–2026 historical sample and alleged "validation"/"holdout" eras have been inspected repeatedly. None qualifies as a pristine independent OOS. Alpha after selection is NOT established. TQQQ did not exist before the 2010 starting date; 1986–2009 cannot be advertised as an observed live-TQQQ backtest.
- Current repository `main`: completed [PR #63](https://github.com/badbuda/stocklense-public/pull/63) and [PR #64](https://github.com/badbuda/stocklense-public/pull/64) — paper-source fingerprint consistency. [#63 green CI](https://github.com/badbuda/stocklense-public/actions/runs/38111961760) **528 tests**; [#64 green CI](https://github.com/badbuda/stocklense-public/actions/runs/38112178833) **533 tests**. All frozen 8.0 code and broker behavior unchanged.

## Quant experiments actually run — do not convert to promotion claims

| Family and reference | Frozen comparator | Fixed challenger results | Gate / decision |
|---|---|---|---|
| [PR #54](https://github.com/badbuda/stocklense-public/pull/54), 5 fixed real QQQ/TQQQ caps, ramps, EWMA shock | 40.026% / -49.076% | Cap2x 30.54% / -45.09%; cap2.5x 35.44% / -46.67%; entry ramp 39.28% / -49.25%; bilateral ramp 39.02% / -51.07%; EWMA5 37.43% / -45.93% | **All 5 rejected**. Even apparently smaller drawdown costs too much CAGR or lacks lag/cost robustness |
| Vol60 continuous target and 5/10-day re-entry/hold (repo `observed_etf_vol60_reentry_audit.py`) | 40.03% / -49.08% | Instant 39.16% / -48.46%; ramp5 39.34% / -48.46%; hold10/ramp10 39.19% / -48.29%, etc. | All 6 rejected; 0/4 required stress cases. 829–1345 modeled trades for some mechanisms vs frozen 147 |
| [PR #52](https://github.com/badbuda/stocklense-public/pull/52), ML meta-leverage | Frozen immutable | Four ML candidates, 106 walk-forward fits; OOS R² **-0.1063** and **-0.1121** in two reused windows | **All rejected**. No predictive alpha established |
| [PR #58](https://github.com/badbuda/stocklense-public/pull/58), real GLD+TLT | 40.0263% / -49.0756% | 85% frozen+7.5% GLD+7.5% TLT: **36.5802% / -43.7717%**; 70% frozen+15% GLD+15% TLT: **32.5180% / -40.1518%** | MaxDD improved 5.30pp/8.92pp, but CAGR fell 3.45pp/7.51pp; both failed 0/4 continuation cases |
| [PR #60](https://github.com/badbuda/stocklense-public/pull/60), **real observed QLD physical ETF**, 4,191 sessions | 40.0263% / -49.0756% | QLD at 2x: 39.8182% / -49.0756%; QLD also for 1.25x: 39.9900% / -48.8257% | Both 0/4, rejected; no synthetic leverage proxy |
| [PR #62](https://github.com/badbuda/stocklense-public/pull/62), official Cboe **observed prior-session VIX closes**, 4,190 matches | 40.0263% / -49.0756% | VIX 30/40-tier: **37.2594% / -54.9315%**; 5-session VIX jump: **38.4368% / -49.1476%** | **Both fail**, worsened MaxDD. Original publication first-seen is not proven |
| [PR #59](https://github.com/badbuda/stocklense-public/pull/59), official NY Fed EFFR effective-date cash | Frozen zero-yield 40.0263% | Conditional EFFR less 200bp: 40.1157%; less 100bp: 40.1848%; full EFFR: 40.2709% | **Not proven cash gain**: assumed two-completed-session timing and broker credit/FX/tax NOT evidenced |
| [PRs #53/#55](https://github.com/badbuda/stocklense-public/pull/55), PIT news integrity and calendar | no eligible news alpha comparator | Valid historical first-seen events: **0 independently authenticated** | Infrastructure/validation improved, **no legitimate historical news alpha**; release/event date is NOT provider first-seen |

References: [SL9-013 sleeve findings](https://github.com/badbuda/stocklense-public/blob/main/research/reports/SL9-013_20261011_FIXED_SLEEVE_FINDINGS.md); [SL9-014 EFFR/crisis](https://github.com/badbuda/stocklense-public/blob/main/research/reports/SL9-014_20261011_EFFR_AND_CRISIS_FINDINGS.md); [SL9-015 real QLD](https://github.com/badbuda/stocklense-public/blob/main/research/reports/SL9-015_20261011_REAL_QLD_AND_CLAUDE_COVERAGE_FINDINGS.md); [SL9-016 Cboe VIX](https://github.com/badbuda/stocklense-public/blob/main/research/reports/SL9-016_20261011_VIX_IMPLIED_GUARD_NEGATIVE_FINDINGS.md).

### Crisis observations, descriptive only

In the fixed 2015-07-20 to 2016-06-27 window the frozen account lost 49.08% vs -41.18% (85%-sleeve) and -32.78% (70%-sleeve); in the 2020-02-19 to 2020-03-16 window, -48.61% vs -42.75%/-36.41%; in the fixed 2021-11-19 to 2022-05-06 window, -47.69% vs -42.47%/-37.31%. These are fixed-window endpoint close-to-close returns, not each portfolio's own maximum peak-to-trough, nor pristine OOS. The largest historical drawdown of each blended portfolio occurred on different dates than the frozen portfolio.

## Exhaustive Claude-idea coverage map

Definitions: **TESTED/REJECTED** = specific predeclared variant families failed established historical continuation screen, not a theorem about the entire idea. **PARTIAL** = limited mechanics or conditional evidence, not a clean finished test. **BLOCKED** = specific indispensable source/execution evidence missing. **UNTESTED** = no qualified direct experiment. **OPERATIONAL** = code/guard exists but deployment/production evidence may be absent.

| Original idea / mechanism | Classification on current verified evidence | Exact next action / why not call it tested |
|---|---|---|
| Real TQQQ vs synthetic 3x QQQ | TESTED for current daily adjusted ETF proxy | Need LEAN exact raw same-input and historical broker executable fills; **do not** extrapolate real TQQQ back to 1986 |
| Fixed leverage cap / Kelly-like throttles | TESTED/REJECTED **specific caps**, PARTIAL mathematical Kelly | No complete Kelly signal with verified causal drift forecast; avoid resweeping 2x, 2.5x |
| Continuous inverse-vol sizing `1/sigma` | TESTED/REJECTED at fixed Vol60 target | No proven robust improvement; trading count/lag matters |
| Inverse-variance sizing `1/sigma²` / fractional Kelly | **UNTESTED directly as a separately preregistered family** | Require independent new sample, verified units (daily vs annual, % vs fraction), realized ETF drag attribution |
| Dynamic volatility-drag budget / expected geometric-return gate | PARTIAL | Day-by-day `log(1+Lr-fee)` arithmetic-vs-drag decomposition, lead/lag null, matched sigma placebo and crisis OOS remain necessary |
| Fast/slow RV, EWMA shock, variance acceleration | TESTED/REJECTED selected EWMA5, Vol60 and shock variants; **PARTIAL** for HAR/downside-semivariance or RV 5/20/60 interaction | Do not imply all volatility forecasting families tested |
| Crash exit, re-entry hold, 5/10-day ramps, staged trades | TESTED/REJECTED specific 3-day and 5/10-session configurations | Distinct gap-time emergency exits need *intraday* observed executable quotes |
| Hysteresis, soft SMA200/trend threshold, trend curvature | **UNTESTED directly** as clean forward challenge | Freeze 8.0 and preregister exact smooth gate **before forward data**, no retrospective SMA fishing |
| No-trade deadband/asymmetric transaction speed | PARTIAL: 50bp band embedded in Vol60 trial | Isolate effect only after proving liquidity and actual fills; costs may overwhelm |
| Portfolio high-water drawdown cap / ruin budget / stop-loss | PARTIAL stress research, direct live risk budget **BLOCKED** | Gap-through-stop, trading halts and leverage path with executable prices; do not assume stop order eliminates gap |
| VIX spot-tier and fast VIX jump overlay | TESTED/REJECTED two rules using official observed Cboe close | Same-day VIX value not available to pre-open trade; no value found from specified lagged rules |
| VIX3M futures term structure, VVIX, SKEW | **UNTESTED/BLOCKED** | Contemporaneous observed futures/index data and lag/provenance, no invented first-seen |
| HY credit spreads, bond-yield curve, term premium and recession releases | **UNTESTED/BLOCKED** | Historical as-of *vintages*, publication timestamps, license/access and look-ahead-free joins (FRED/ALFRED source check) |
| Breadth/sector participation/correlation concentration | **BLOCKED** | Survivorship-safe historical Nasdaq constituents, index reconstitutions, lagged volume/prices |
| Gold + Treasury fixed satellites, cross-asset buffer | TESTED/REJECTED for two **fixed GLD/TLT** mixes | These mixes reduce drawdown but fail growth hurdle. Other assets/methods not proven |
| QLD instrument substitution vs QQQ/TQQQ | TESTED/REJECTED two fixed variants | QLD actual daily 2x goal differs from multi-day 2x. Need independent quote/fee data before claiming implementation benefit |
| SOXL, UPRO, managed-futures, commodity/FX trend | **UNTESTED** | Different underlying index and risk benchmark; avoid treating as mere NASDAQ leverage substitution |
| Put options, collars, variance futures, tail hedges | **BLOCKED** | Contemporaneous bid/ask option surfaces, expiries, roll transaction costs, IV skew, funding and early assignment risks |
| Historical financing-aware leverage | PARTIAL: EFFR hypothetical cash accrual | Actual broker margin tiers, cash credits, FX/tax, corporate actions and borrowing terms missing |
| Fixed cash sweep/high-yield reserve | PARTIAL conditional accounting | Never label full EFFR as cash received by Excellence; broker terms and verified funding clocks needed |
| ML meta-leverage and predictive return regime | TESTED/REJECTED four fixed candidate models | 106 refits, negative R²; need truly new features and fresh forward refits, not repeated tuning |
| ML text / sentiment / corporate events | **BLOCKED** | True historical archive first-seen and ex-ante target label/revision controls |
| FOMC / CPI / Fed rate-surprise event filter | **BLOCKED** | Pre-release consensus vintage, schedule published pre-event, provider observation+execution latency, past-only matched controls, cluster bootstrap |
| SEC M&A/buybacks/earnings event layer | **BLOCKED** | SEC acceptance timestamp alone does not prove earliest public availability; immutable collector observation required |
| Wars/elections/geopolitics and corporate press headlines | **BLOCKED** | Timestamped contemporaneous source, causally defined surprises, counterfactual controls; no event-alpha conclusion |
| Seasonality, election cycle, century-cycle charts | **UNTESTED** as a defensible PIT model | Scientific pre-registration and independence; don't mine retrospective calendars |
| Fundamental CompanyScore earnings/FCF/valuation/quality and survivorship | **SEPARATE stock-selection research system, NOT direct frozen ETF 8.0 experiment** | Sharadar-like PIT fundamentals with restatements, delisted names, universe snapshots, selected-value and multiple-testing audit |
| Exact LEAN original order/fill ledger parity | **BLOCKED** | Same-commit raw original LEAN orders, fills, equity, holdings, timestamps, underlying data digests; shadow model ≠ QC historical fill |
| Adjusted Yahoo prices and corporate actions | PARTIAL source digest/XNYS completeness | Independent vendor cross-check, split/distribution cash accounting, corrected vintages and original immutable feed |
| Daily OPEN vs 09:31/09:32 NBBO/VWAP/market impact | **BLOCKED**; a **single 2026-10-09 Yahoo 1-minute BAR OPEN journal session** exists | Never call 1m BAR OPEN a contemporaneous quote or an actual fill. Require independent NBBO/volume and fills |
| Broker reconciliation, partial fills, lost ACK, order UUID, idempotency | PARTIAL local simulation/transaction safeguards, real broker sandbox **BLOCKED** | Read-only broker export first, sandbox rejects and disconnect tests; never auto-order |
| AWS EventBridge runtime + Lambda levels/NO_CHANGE reconciliation | PARTIAL / CODE MERGED; live deployment independently unverified | Compare real DynamoDB/CloudWatch receipts & OIDC/S3 object archival evidence |
| Atomic paper ledger + crash recovery | PARTIAL, local code PR #11; cross-run durability **BLOCKED** | GitHub runner is ephemeral, need durable journal and recovery proof |
| SNS missed-invocation/NYSE holiday aware dead-man alarms | **PARTIAL/BLOCKED** | Actual received alert test, one disabled schedule detection, half-day/holiday and publication delays |
| Prospective 8.0 and challenger paper matched evidence | PARTIAL: 10 registered challenger-date rows, 2 frozen paper sessions, **0 paired independently qualified forward paper sessions** | 63-session review checkpoint then 252-session assessment, prove immutable capture and missing session reason |
| Prospective source fingerprint / definition mutation controls | **CODE IMPROVED** [PR #63](https://github.com/badbuda/stocklense-public/pull/63) + [PR #64](https://github.com/badbuda/stocklense-public/pull/64) | Definition mismatch => BLOCKED; historic evidence fingerprint mismatch => ATTENTION; source reconciliation unresolved |
| Raw historical news provenance and completed NYSE session forward horizons | **CODE IMPROVED** [#53](https://github.com/badbuda/stocklense-public/pull/53), [#55](https://github.com/badbuda/stocklense-public/pull/55) | Cannot use official release timestamp or self-asserted vendor field as authenticated first-seen; sample size still zero |
| Portfolio/drawdown beta-matched QQQ/SPY and independent alpha inference | PARTIAL: observed QQQ matched source and HAC-type regressions | No selection-corrected multiple hypothesis SPA/Romano-Wolf proof or clean OOS |
| Dashboard / MCP monitoring and Signal Health | PARTIAL, native evidence files available | Dashboard freshness and actual production deployment require independent UI/API observation; don't interpret a green unit test as live uptime |

## Forward/Paper reality, verified public artifacts

Source-of-truth `docs/backtest_live_readiness.json` explicitly has `status=BLOCKED_FOR_LIVE_TRADING`, with **10** prospective challenger-session records, **2** frozen simulated Paper ledger sessions, **0 paired forward independently qualified sessions**, **0 broker execution observations** (`docs/execution_observation.json`). A 2026-10-09 one-session 09:30/09:31/09:32 observed **Yahoo minute-bar OPEN** journal exists, but bid/ask NBBO and real fills remain absent.

Important current registry discrepancy: registered SL9-007 evidence fingerprint `ffd63bf6988f51442f2ff2232fbace4054b55e88d8afe968e4817759d274897d` vs research queue `995ffc17a889c63d3fcc68376a2b9a688f038c6866820e6baace660e67d02528`. Definition fingerprint `b6c7a09db9bfb74ed323f36f8cfe1fbcc34d0962cea7fade1fdcfffbf7779fb7` still matches. Mismatch existed in registry history by 2026-10-09 and persisted through 2026-10-10; reason/immutability receipts not independently reconciled. New #63 freshness and #64 maturity gates prevent a silent verified-forward status. Their 528/533 green test results establish code behavior only, **not** archived original capture proof. Confirm actual journal history rather than rewriting registration or backfilling missed orders.

## Claude — requested review tasks and answer format

1. **Audit the frozen accounting/source chain first.** Identify exact raw artifacts required to test LEAN↔Python daily signals, open fill ledger, split/dividend adjustments and cash/fees; reconcile all daily deltas, earliest executable timestamps, separate production vs research schedules. Do not interpolate TQQQ pre-2010.
2. **Rank at most three truly distinct untested hypotheses**, not variants of failed lagged volatility caps. For each provide precise economic mechanism, available *point-in-time* data, immutable preregistration, 0/1/2-session lag, 10/20/30bps fills/costs, block/bootstrap and leave-one-crisis-out/multiple-testing null, and specific early-falsification gates. Do not choose the eventual "best" threshold on already mined years.
3. **Challenge the cash interest report**: compare separate broker contract to EFFR *effective-date* sensitivity, holiday-accurate accrual and actual cash balances, negative cash/margin conventions, taxable funding/currency spread; don't claim +0.245pp CAGR is realizable cash alpha.
4. **Determine whether the Paper fingerprint mismatch is a benign source refresh or evidence invalidation** by identifying original change commits, archived market-data bytes and timestamps. Do not reset the original fingerprint or declare same-day availability from a date-only CSV.
5. **Specify source acquisition, not fabricated backtests, for pending breadth/HY/VIX term structure/SEC-GDELT-FOMC-CPI options.** Cite provider timestamp/vintage semantics and actual license constraints. Where an input is unavailable, classify BLOCKED and propose an independent prospective capture plan.
6. Deliver a table `Hypothesis | Original timestamp-qualified input | Mechanism | Baseline matching | Costs/latency | Predeclared rejection rule | Current evidence | Hard blockers` and say **NO PROVEN ALPHA** unless source, execution and forward evidence justify otherwise.

## Operational boundaries (non-negotiable)

- StockLens 8.0 and historic investment decisions: immutable.
- New leveraged ETF performance: actual observed TQQQ, never synthetic 3x QQQ.
- CI: batch substantive changes; no repeat runs of unchanged failed hypothesis; draft PRs until their **actual** CI/artifacts examined.
- No invented true vendor-first-seen dates, APR entitlement, statistical alpha, 09:31 NBBO, broker fills or capital authorizations.
- No live order submission, broker credentials in public GitHub, automated strategy promotion, or implied certainty from 5–10-year holding period.
- Track immutable paper evidence; missing days are gaps, never retroactive filled trades.

Latest related action plan: [Issue #61](https://github.com/badbuda/stocklense-public/issues/61) and [live readiness Issue #3](https://github.com/badbuda/stocklense-public/issues/3), [forward external-audit Issue #10](https://github.com/badbuda/stocklense-public/issues/10).


## Additional directly tested Claude mechanisms — SL9-019 (completed after first handoff draft)

- [PR #65 — true observed ETF inverse-variance vs downside semivariance](https://github.com/badbuda/stocklense-public/pull/65), merged after [CI #38112459649](https://github.com/badbuda/stocklense-public/actions/runs/38112459649) **538 passing pytest tests and 8 artifacts**. [Original result artifact](https://github.com/badbuda/stocklense-public/actions/runs/38112459649/artifacts/11691663638).
- Physical real QQQ/TQQQ bar source unchanged, frozen portfolio NAV day-by-day parity. Two direct fixed rules with prior completed QQQ 20-session realized log-return sigma:
  - Inverse variance: cap leverage to `clip((0.60/sigma20)^2,1,3)`, at most frozen 8.0 leverage. CAGR **39.8642%**, MaxDD **-49.0756%**, **-0.1621pp CAGR**, **0pp MaxDD benefit**, **177** modeled trades, **0/4** continuation checks passed.
  - Downside semivariance: cap `clip(0.60/sqrt(2*252*mean(min(r,0)^2)),1,3)`. CAGR **37.3498%**, MaxDD **-47.7857%**, **-2.6765pp CAGR**, **+1.2899pp MaxDD**, **1,010** trades, **0/4** checks passed.
- Therefore the **specific inverse-variance20 and downside-semivariance20 variants are now TESTED/REJECTED**, rather than UNTESTED. This does **not** constitute a test of full forward drift estimation, Kelly-optimal dynamic leverage or all tail-hedge families.
- After PR #65, frozen 8.0 remains the highest-CAGR among these tested historical candidates. No live-fills, separate clean OOS, new alpha, or capital authorization. Follow-up should target new source information and forward execution realism, not ex-post optimizing 20-session window or 60% target.

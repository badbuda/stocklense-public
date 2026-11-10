# StockLens research intake — TQQQ cash-secured put / rolling / protective-put video
**Date:** 2026-11-10 · **Decision:** add a research challenger, NOT production · **Jira:** SL-61

## What the video actually reports
The narrator recounts nearly 1,400 days (Jan 14 2022 through around Nov 2025) of **cash-secured TQQQ short puts**, support-selected strikes, opportunistic rolls down and out in weakness / up in recovery, occasional **long-duration protective puts**, and stopping new short puts after acquiring TQQQ shares via assignment. A separate poor-man's-covered-call position coexisted and is not counted in the reported table.

**Reported** cumulative P&L for short-put/long-protection portion: **+$11,572** by near-November 2025; negative roughly $115 after 399 days in early 2023. This is a video self-report, **NOT independently audited total account equity, CAGR, or risk-adjusted return**. The video does not provide a full transaction log, capital tied up per day, assigned share mark-to-market P&L, net long-put cost, roll-by-roll debits/credits, annual tax, or an algorithmic strike/roll definition. Lack of these precludes exact replication.

**Illustrative specific trade (not independently verified):** 5 × TQQQ $70 Nov 21, 2025 short puts, stated premium $1.42/share. Five standard 100-share contracts would collateralize **$35,000**, produce **$710 gross premium**, effective expiry breakeven **$68.58**, and worst-case expiry loss from the short-put leg alone **$34,290** if TQQQ were worth $0. The narrator also describes roughly $600 from a combined monthly roll; do not equate that amount to the standalone $710 gross premium. Whether the particular contracts had adjustments/multipliers requires verification.

**Self-report data limitations:**
- A positive running column of option cash flows is not total mark-to-market wealth across the cash reserve, short positions, long protection, assigned stock and separate call position.
- Rolling losses down/out does NOT erase losses; closing one short put and opening another creates new cost/premium and extends risk.
- At put expiry, credit minus max(strike - underlying price,0), times 100 shares/contract, is the unhedged payoff; mark-to-market and American assignment are more complex.
- Short-put income is capped at collected premium but large downside remains. Since TQQQ seeks **3× DAILY** Nasdaq-100 movement, cumulative returns can differ dramatically with path and volatility. The risk cannot be assumed to disappear because QQQ does not reach zero.
- Support/resistance discretion, long puts and assignment/roll decisions are too unspecified to implement *faithfully*. Do not invent 2022–25 option premiums.

## Data availability in StockLens (as inspected in current main)
Frozen observed data: `research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json` includes 4,191 actual daily QQQ/TQQQ adjusted OPEN/CLOSE and frozen leverage decisions. It **does not** include historical TQQQ options strike-expiry-timebid-ask snapshots, actual long-put hedge prices or assignment events. There is no known historical option-chain dataset/option payoff engine in the indexed repository tree.

Potential licensed vendor source: [Cboe DataShop Option EOD Summary](https://datashop.cboe.com/option-eod-summary) lists historical U.S. ETF option NBBO snapshots from January 2012, volume/open interest and optional Greeks/IV. Vendor licensing, bid/ask at 15:45/EOD, first-seen timestamps and contract adjustments must be validated before it becomes backtest evidence. [OCC cash-secured put](https://www.optionseducation.org/strategies/all-strategies/cash-secured-put) and [OCC assignment](https://www.optionseducation.org/referencelibrary/faq/options-assignment) explain capital and early-assignment risks; [ProShares TQQQ](https://www.proshares.com/our-etfs/leveraged-and-inverse/tqqq) states the 3× DAILY objective.

## Research implemented now in [draft PR #174](https://github.com/badbuda/stocklense-public/pull/174)
A deliberately narrow **price-only observation**: from each frozen daily StockLens signal, assume an underlying entry at next observed adjusted TQQQ OPEN, then examine forward **21-session** adjusted TQQQ CLOSE against a put strike **10%, 20%, 30%** out of the money. Split into frozen 8.0 **cash=0**, **risk-on**, **3×**, middle exposure, 2022, 2024, plus sensitivity of every-21-session non-overlapping entry grid. Report frequencies of expiry ITM, any interim observed CLOSE breach, and hypothetical cash-collateral erosion **EXCLUDING all premium and hedging**.

This is **NOT a backtest of options**, because no actual historical premiums, quotes, rolling flows, assignment or long-put protection are available. An ITM proxy is not an assignment probability, and split-adjusted underlying prices are not executable option contract data. No true profit-return or tax comparison can be claimed.

## What to run once valid option-chain data is sourced
1. Frozen StockLens 8.0 alone, same start wealth and daily funding.
2. CSP-only using defined support/strike method and 30 DTE.
3. CSP in StockLens **0× cash** regime (explicitly measure the extra downside risk overriding cash safety).
4. CSP only on small, collateral-funded cash sleeve when StockLens **risk-on** and exposure/collateral caps permit.
5. Every previous variant ± rolling, ± protective long puts, then pairwise and full factorial if sample supports it.

Predeclare deterministic entry/exit/roll rules, validate data vendor and corporate actions, replay historical option **executable** bid/ask with hedge MTM, enforce collateral/assignment, model broker tax/FX, after-tax terminal wealth, 2022 crisis, extra lag and OOS. Frozen 8.0 must not be mutated and no automatic promotion.

**Deployment gate:** `BLOCKED_DATA_OPTIONS_QUOTES`; **No option-strategy return/backtest has been claimed**. Even after quote data is obtained, original creator's adaptive support/roll logic is still `BLOCKED_UNSPECIFIED_RULES` until documented.


## Observed underlying-price stress executed, 2026-11-10

An independent JavaScript calculation fetched the *exact* frozen observed TQQQ daily bars and computed all 3,970 eligible 21-session windows from 2010-11-26 to 2026-09-10. The reported **20%-below-next-open hypothetical strike** is NOT the creator's actual support strike, and does not use options quotes. Signal level is frozen StockLens 8.0 from previous completed session.

| Cohort | Overlapping windows | Future expiry-close below 20%-OTM strike | Any intervening DAILY CLOSE breach |
|---|---:|---:|---:|
| All states | 3,970 | 7.03% | 14.18% |
| Frozen 8.0 cash=0 | 274 | **17.88%** | **30.29%** |
| Frozen 8.0 risk-on | 3,696 | 6.22% | 12.99% |
| Frozen 8.0 3× | 3,216 | 5.38% | 11.01% |
| Year 2022 | 251 | **34.66%** | **55.78%** |
| Year 2024 | 252 | 3.97% | 9.92% |

Non-overlapping 21-session fixed-grid sensitivity: all = 190 windows with **7.89%** expiry-close-below-strike; frozen cash = only 14 grid windows with 14.29% breach (**too few** for reliable inference); 2022 = 11 grid windows with 27.27% breach. The high-risk cash cohort includes substantial 2022 overlap, and is NOT a causal proof that a signal predicts option returns. Results were calculated on observed underlying bars, no premium or roll data and no trading/assignment.

**Unhedged short-put intrinsic-loss risk at expiry excluding any premium**: among all overlapping 20%-OTM 21-session windows, mean conditional on *all* windows (including zero-loss) is 0.79% of put strike cash collateral, worst expiry stress 62.16% of collateral. These values are NOT net option profit, because actual premiums, margin rates, hedges and early assignment are missing. Actual profit could differ substantially.

**Sanity check for the narrator's single video trade:** 5 standard contracts × 100 shares × $70 strike = $35,000 collateral. 5 × 100 × $1.42 stated premium = $710 gross. At hypothetical expiry $50, unhedged short-put P&L $710 − (70−50)×500 = **−$9,290**; at $0 **−$34,290**; at $70 or higher **+$710**. Does not include long protective puts, previous rolls, stock inventory, broker fees or tax. This is arithmetic, not proof those trade quotes were actually executable.

**Research decision:** cash-secured TQQQ puts on frozen **0x cash** days can materially re-introduce losses. Do not promote a cash-sleeve strategy using only observed underlying prices. Need licensed full historical options quote legs and predefined support/roll/hedge rules before evaluating CAGR, total equity or after-tax performance.


## Follow-on: genuine option quote readiness / premium threshold / collateral opportunity cost

**Status (10 Nov 2026):** implemented **research-only** option-chain intake / accounting engine and tested it against **SYNTHETIC UNIT FIXTURES**, plus two additional observed-TQQQ price-only hurdle and financing analyses. No real historical option premium series was acquired, so no option-strategy backtest, CAGR or "alpha" can be claimed.

### Provider verification

- [Cboe Option EOD Summary](https://datashop.cboe.com/option-eod-summary): documented from January 2012, quote snapshots **15:45 ET + EOD**, bid/ask sizes and OI, optional Greeks. Licensed purchase required. This is the most direct source for a proper 2012–2026 TQQQ options-price replay, subject to symbol-specific coverage, adjustment and license validation.
- [ORATS Historical Data API](https://orats.com/docs/historical-data-api): historical near-EOD strikes API from 2007; [pricing](https://orats.com/data-api) lists USD 199/month delayed plan (as reviewed 2026-11-10); a separate vendor, different quote timing, not identical Cboe evidence.
- [Massive historic options data](https://massive.com/knowledge-base/article/how-much-historical-stock-data-does-massive-have): options *quote* data from **2022-03-07**, so cannot validate earlier 2010–2021 quotes or January 2022 entry. Historical bars/trades exist from 2014 but cannot be silently substituted for executable NBBO quotes.
- [Cboe FAQs](https://datashop.cboe.com/faqs) explains roots containing digits denote adjusted contracts with nonstandard deliverables. The engine explicitly refuses such contracts until independently proven OCC deliverables, adjusted contract counts and splits are modeled.

**No paid license, key, or options data was purchased or requested; data coverage is therefore not yet qualified.**

### Exact new code/tests

- \`research/tqqq_cash_secured_options_ledger.py\`: fail-closed 15:45 Cboe-CSV importer, strict TQQQ root/expiration/strike/bid/ask/size/OI and independently reviewed contract-adjustment flag. Research ledger with cash backing, baseline-0x no-sell gate, configurable max collateral sleeve (default 15%), ask-to-close/bid-to-sell, atomic roll-down-and-out (explicit net debit/credit), funded long-put hedge, expiry assignment and conservative mark-to-market. It **does not** simulate early American assignment, actual broker fees/commissions, split conversion across live contracts, taxes or full multidate selection/roll strategy.
- \`tests/test_tqqq_csp_quote_ledger.py\`: **9 synthetic fixture tests PASS** — including strict 0x gate, insufficient collateral, marking quote freshness, down/out roll cost, long-put cost, terminal assignment and rejection atomicity/adjusted roots.
- \`research/stocklens_csp_premium_hurdle_20261110.mjs\`: observed adjusted underlying TQQQ only; computes strike intrinsic loss hurdle, conditioned on frozen 8.0 exposure, for theoretical strikes 10/20/30% below each observed entry OPEN and 21-session end CLOSE. **NOT real option premium**.
- \`research/stocklens_csp_collateral_opportunity_cost_20261110.mjs\`: exact frozen 8.0 same-capital next-open replay with cash sleeve reserved at each baseline level change (fixed fractional *starting value at transition*, drifting between transitions). No put income included. All combinations keep 0x risk defense unchanged.
- \`.github/workflows/stocklens-csp-quote-gate.yml\`: CI test + underlying hurdle + financing analysis, archive JSON.
- [CI PASS: option quote ledger & cash allocation](https://github.com/badbuda/stocklense-public/actions/runs/42778549712) (previous run had 9 tests PASS), [updated CI PASS](https://github.com/badbuda/stocklense-public/actions/runs/42778549712), [machine-readable hurdle and collar opportunity cost](https://github.com/badbuda/stocklense-public/actions/runs/42778549712/artifacts/13744882082).

### Intrinsic loss hurdle *excluding premiums*

These values are **ex post average intrinsic strike liability as % of hypothetical cash collateral**, at expiry on each 21-session TQQQ underlying scenario, NOT required or realized real option premiums and NOT profitability estimates. Actual option premiums could rise substantially with 2022 volatility.

| Fixed theoretical strike 20% OTM | Overlapping observations | Mean intrinsic liability / strike collateral | Fixed 21-day disjoint observations | Disjoint mean |
|---|---:|---:|---:|---:|
| All frozen states | 3,970 | 0.7851% | 190 | 0.9225% |
| Frozen 0× cash | 274 | 1.7375% | 14 | 1.0703% |
| Frozen risk-on | 3,696 | 0.7145% | 176 | 0.9108% |
| 2022 all states | 251 | **4.1619%** | 11 | **2.9966%** |
| 2022 0× cash | 174 | **2.7360%** | 8 | **1.8730%** |
| 2024 all states | 252 | **0.3765%** | 12 | 1.3354% |

**Video single quote** 1.42/70 = **2.0286% premium/collateral** for one stated 2025 put. Applying this *same* 2.0286% to all months as if it were a historical premium is NOT legitimate; it's only an **illustrative price stress**. E.g. hypothetical 2022 all-state intrinsic liability hurdle of 4.16% exceeds the isolated 2.03% example. Overlapping windows are not independent trades, and disjoint year-2022 n=11 is too small to make robust claims.

### Same-capital financing opportunity cost of reserving a cash sleeve

On identical frozen 8.0 signals, observed daily QQQ/TQQQ adjusted next-OPEN fills, same $100k initial cash, whole shares, 2bps fees + 10bps modeled slippage per leg, zero cash interest, **NO option revenues or liabilities whatsoever**. At each frozen exposure change, reserve 10/15/25/35% of current transition equity as cash, reducing risk-on investment from baseline 98.5% to 88.5/83.5/73.5/63.5%. Between transition dates, ring-fenced proportion drifts: *not* daily 15% maintenance and not a complete collateral-risk ledger.

| Cash sleeve at exposure transitions | CAGR | MaxDD | CAGR difference vs frozen (pp) |
|---|---:|---:|---:|
| 0% frozen reference | **39.84%** | −49.08% | 0.00 |
| 10% | 36.60% | −47.23% | −3.24 |
| 15% | 34.93% | −46.25% | −4.90 |
| 25% | 31.49% | −44.12% | −8.35 |
| 35% | 27.89% | −41.73% | −11.94 |

The narrator's *one* five-contract $70 CSP requires **$35,000 collateral**, 35% of a $100,000 baseline portfolio. Since frozen 8.0 typically invests 98.5% on risk-on days, this collateral cannot be **double counted** as already deployed in TQQQ. The opportunity cost above has to be compensated by actual net income from options, after commissions, assignment, long-put protection, FX and Israeli taxes, before claiming improvement.

### Decision / boundaries

No capital deployment, no live trading or AWS changes, no model promotion. The current engine is **ready for third-party historical quote ingestion after validated entitlement and contract-adjustment audit**, *not ready to label any options strategy profitable*. Next real blocker is independently licensed TQQQ full EOD chain (2012–2026) with OCC contract deliverables and executable quotes, plus source-specific strike/roll/hedge rules. Upon supplying that licensed dataset, run the full marked-to-market options allocation jointly with frozen 8.0, evaluate holdout and after-tax net final equity, and compare on **same total capital**.

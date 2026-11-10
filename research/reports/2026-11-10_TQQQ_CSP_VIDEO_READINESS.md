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

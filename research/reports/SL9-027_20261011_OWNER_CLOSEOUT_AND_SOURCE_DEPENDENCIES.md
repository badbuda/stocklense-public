# StockLens — owner closeout and source-dependency ledger (2026-10-11)

**Boundary:** all repository changes that could be completed with existing
connected GitHub evidence and permissions; this is NOT an operational
go-live declaration. The user owns Excellence Trade contract terms.
Frozen StockLens 8.0 is unchanged. No real broker orders/positions, no
model promotion, no synthetic TQQQ performance.

## Completed and verified

| Deliverable | Proof | What this does NOT prove |
|---|---|---|
| Old diverged PR #2: correct monthly cashflow-neutral NAV drawdown, raw DD separately, exhaustive zero-contribution 21/63/252/756/1260 market-session windows and joint 3x3 signal lag/slippage | [PR #69 merged](https://github.com/badbuda/stocklense-public/pull/69); [CI #38121558939](https://github.com/badbuda/stocklense-public/actions/runs/38121558939), **569 tests passed** | Historical trading prices still Yahoo-adjusted daily OPEN, not actual executable quotes or broker fills |
| Old diverged PR #5: archived read-only AWS signal journal SHA, UTC generation/recording time, frozen 8.0 mode/weights and disabled broker actions with adversarial tests; original XNYS calendar guard and modeled-paper audit retained | Same #69; post-merge read-only AWS main [CI #38121664048](https://github.com/badbuda/stocklense-public/actions/runs/38121664048) success | CI was a weekend/identity/table preflight; not proof of on-session Monday archival completeness or independent AWS Object Lock |
| Frozen-8-only forward recording contract: complete/missed XNYS chain, signal/underlying digests, pre-open timing boundary, modeled source vs broker distinctions | [PR #70 merged](https://github.com/badbuda/stocklense-public/pull/70), [green CI #38121841062](https://github.com/badbuda/stocklense-public/actions/runs/38121841062) | External WORM signer not deployed. Local self-asserted external receipt fields do not establish third-party attestation; model returns `independent_external_verification_performed=false` |
| Hard block of legacy 20/63/252/500 count thresholds: 0 qualified frozen8 forward sessions, no historic old SL9-007 proxy rows promoting performance or live-readiness | [PR #73 merged](https://github.com/badbuda/stocklense-public/pull/73), [CI #38122132224](https://github.com/badbuda/stocklense-public/actions/runs/38122132224), **579 passed** | 63-session clock has NOT started on independently verified external receipts |
| One-day official Cboe VIX/VIX3M overlay | [#67 rejected/closed](https://github.com/badbuda/stocklense-public/pull/67) with 552 green tests | Not a winning defense; 0/4 cost+lag continuation gates |
| Claude H2 two-day prior-close backwardation (>1 two completed sessions), frozen 3x capped to 2x, source-pinned official Cboe index observations, real historical QQQ/TQQQ ETF open proxy | [PR #74 merged](https://github.com/badbuda/stocklense-public/pull/74); [green CI #38122519599](https://github.com/badbuda/stocklense-public/actions/runs/38122519599), **585 passed**, exact Cboe source archive SHA256 `0ff8ef25ee51388e39d53378fad2ba233b8e9e7c5fa55cf765e550a399c77749` | Historical reused data, no pristine OOS, index not VIX futures, no broker execution, no valid multiple-testing-adjusted p-value |
| Duplicate stale contracts / old PRs cleaned | #2/#5 closed after #69 port; #71/#72 closed after choosing one #70 contract + incremental #73 guards | No speculative merging of diverged branches or extra competing forward model |

### H2 exact negative result from green CI

| Frozen / challenger | CAGR annual | MaxDD | Trades |
|---|---:|---:|---:|
| Frozen 8.0 | 40.026317% | -49.075618% | 147 prior baseline |
| Two-day index backwardation 2x cap | **38.206483%** | **-48.750371%** | **251** |

Candidate: **74** intervened sessions; 0 of 4 historical continuation gates passed.
Gross-return permutation diagnostic (1,000 seed 20261011) matched 74 intervention DAYS
of 3,384 frozen 3x-eligible sessions, but **did not match episode length or
turnover** (placebo median 435 trades vs candidate 251). Observed no-fee
CAGR delta **-1.3366 pp**, placebo mean **-0.2259 pp**, one-sided descriptive
tail fraction **0.936064**. This is **NOT a corrected causal significance test**.

### Claude's remaining two source-dependent hypotheses

**H1 — High-yield credit spread slow shock: SOURCE BLOCKED.**
The official FRED/ALFRED series `BAMLH0A0HYM2` (ICE BofA US High Yield
Index Option-Adjusted Spread) is real daily corporate-credit data:
https://alfred.stlouisfed.org/series?seid=BAMLH0A0HYM2 .
The official series now explicitly states that **from April 2026 it includes
only three years of observations**; its ALFRED public release-dates table
shown here starts **2023-10-10**, not verified vendor first-seen vintages in
2010–22. ICE data have copyright and usage restrictions; license terms
apply even when FRED/ALFRED front ends are readable. Do not treat
`ALFRED has download-vintage controls` as evidence of a complete
2010–2026 legally usable, timestamp-certified series. This does NOT mean
the proprietary pre-2023 data do not exist — they are **not available
and permissioned through currently qualified project evidence**.
Result: no legitimate complete historical test of the predeclared
20-session increase vs trailing 1,260-session 90th-percentile H1.
Alternative daily-rate series would be a **new predeclared hypothesis**,
not H1 data substitution.
Official: https://fred.stlouisfed.org/series/BAMLH0A0HYM2
and https://alfred.stlouisfed.org/series/downloaddata?seid=BAMLH0A0HYM2 .

**H3 — Nasdaq Opening Cross vs 09:31 NBBO/TWAP: DATA/ROUTING BLOCKED.**
Nasdaq officially defines the 09:30 ET Opening Cross, its NOOP and
Market-On-Open (MOO) order type:
https://www.nasdaqtrader.com/trader.aspx?id=openclose
and https://listingcenter.nasdaq.com/rulebook/Nasdaq/rules/Nasdaq%20Equity%204 .
Nasdaq Rule 4702 describes MOO submission immediately prior to **09:28 ET**
and modification/cancellation time immediately prior to **09:25 ET**;
specific broker routing/cutoffs may be earlier. Public OHLC daily OPEN
and Yahoo 09:31 one-minute bar OPEN are NOT historical NBBO bid/ask/size
or actual executed MOO receipts. Historical bid/ask data is a separate
licensed source; e.g. https://databento.com/pricing/ describes
market-data usage/labeled pricing, not entitlement already connected.
We have **no** licensed archived 09:31 NBBO stream or proven Excellence
MOO routing; no H3 execution-improvement percentage may be stated.

### Other genuine open evidence, not programmer to-do list

1. **Prospective external receipts:** deploy an independent immutability
   witness/third-party time source or correctly configured separate AWS S3
   Object Lock compliance store; verify its policy, IAM separation, retention,
   server time and append-only object receipts. **Currently not deployed or
   independently audited.** Code cannot make a third-party witness exist.
2. **Forward sample:** future XNYS sessions from the next available date,
   external immutable signal receipt before open, real observed QQQ/TQQQ
   source bytes and complete-or-MISSED session logs. No retrospective
   backfill. 63 sessions is an operations-only evidence checkpoint, not
   statistical investment validation. Current independently attested
   frozen8 real ETF forward sessions: **0**.
3. **Original SL9-007 fingerprint:** registry `ffd63bf6...` vs queue
   `995ffc17...` remains UNRESOLVED. 4 original 8–10 Oct ZIPs are
   safely preserved in the user's Files Library, but they contain
   adjusted ETF observation files with 4189/4190/4191 rows — not
   proof of the exact original 4292-row `research_data_adapter._sha`
   input and creation-time market-data receipt. Never reset registration.
4. **Actual brokerage conditions:** user-owned Excellence fees, FX,
   sweep USD interest, settlement and margin eligibility. Nothing in
   the preceding repo work proves broker-executable P&L.
5. **Corporate/seasonal/tax and independent cross-provider audits:**
   raw split/dividend histories, independent adjusted price checks,
   actual fills/trading routes; contingent on external source contracts.
6. **News/macro PIT:** archived independent first-observed time,
   pre-release consensus vintages, 2010–26 survivorship checks;
   no qualified observations at present.

### Decisions and stop rules

- Do not start another VIX/RV parameter sweep on the same already-selected
  2010–2026 sample. H2 rejected. No cherry-picked in-sample promotion.
- Readiness remains **BLOCKED_FOR_LIVE_TRADING**. Neither future 63/252 counts
  nor technical green CI can authorize capital.
- Next coding only when a real new data source/immutable recipient is
  authorized and can provide demonstrable receipts. Do not silently use
  synthetic TQQQ or continue claiming 40% future guaranteed returns.

**The remaining work is fundamentally independent observations, entitlements
or new future sessions; not currently closable by code alone.**

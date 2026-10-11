# SL9-015 — Claude hypothesis coverage ledger / new observed QLD study

2026-10-11 — written before the first PR experiment run. Keep frozen StockLens
8.0 unchanged. Distinguish COMPLETE, PARTIAL, BLOCKED vs UNTESTED; avoid
repeatedly testing the same overfit idea. Historical analysis is reused 2010–26.

| Claude research direction | Current evidence | Coverage | Honest next gate |
|---|---|---|---|
| Observed real TQQQ vs synthetic paper 3x | SL8 / SL9 real QQQ-TQQQ snapshot, 4191 sessions | COMPLETE for daily-open proxy; NOT LEAN live parity | Real 09:31/09:32 fills + broker quotes |
| 2x QLD instead of half QQQ/half TQQQ | Prior 7.x instrument parity discussion existed; not in current frozen 8.0, same cost/lag 2010–26 engine | NEW FIXED TEST IN THIS PR | Real full QLD bars; do not infer equivalence over multi-day horizons |
| 1.25x QQQ+QLD vs QQQ+TQQQ blend | Different physical ETF tracking and costs, not previously covered in current 8.0 exact frozen ledger | NEW FIXED TEST IN THIS PR | One-year and lag/cost stability checks |
| Financing cost, cash credit and broker sweep | SL9-014 official EFFR effective-day conditional sensitivity | PARTIAL | Real contract cash sweep, FX, tax, commission; no invented first-seen |
| Kelly, caps and volume volatility drag | SL9-009 risk caps, SL9-010 Vol60, independent sensitivity | PARTIAL / no winning verified candidate | Avoid another parameter sweep; independent future sample |
| Transition ramps, shock exits, waiting/re-entry | SL9-009 fixed ramp, SL9-010 Vol60, prior risk studies | TESTED families REJECTED in observed ETF proxy | Actual intraday executable data before testing immediate stop |
| VWAP, 09:31/09:32, order book, broker slippage | Daily OPEN only and execution forensics | BLOCKED | Minute-level observed historical NBBO and brokerage fills |
| VIX term structure, VVIX, SKEW, HY spread, yield curve | Older overlay studies exist; no qualified source in current frozen ETF proxy | PARTIAL | Independent PIT timestamped series, predeclared thresholds |
| Breadth, Nasdaq sector participation | No survivorship-safe constituent history | BLOCKED | PIT constituents and volume universe history |
| Alternative trend SMA lengths / smooth threshold | 8.0 frozen SMA50/200; 3-day ramps tested but distinct smooth boundary not cleanly tested | UNTESTED direct; high reuse/overfit risk | New forward paper sample, no opportunistic hindsight tuning |
| Gold/TLT diversifier | SL9-013 fixed real GLD/TLT + SL9-014 crisis days | COMPLETE as historical reuse, both rejected; provider still unaudited | Independent price audit and forward paper |
| Cash hedge + options / put and futures overlays | No real options surface/spreads/costs | BLOCKED | Historical option prices, spreads and financing |
| ML meta leverage | PR #52, 106 fits, negative test R2 | FAILED | Genuine new data / future forward labels |
| FOMC CPI event surprise and news | PR #53 and #55 PIT integrity; sample 0 independently eligible first seen | BLOCKED | Pre-release consensus, true archived first seen, causal controls |
| Corporate acquisitions, SEC filings, election/war headlines | Same PIT weakness, structural drift and selection | BLOCKED | Source with independently verified earliest tradable availability |

### SL9-015 fixed preregistered study

1. Source: actual observed ProShares QLD Yahoo auto-adjusted DAILY OPEN/CLOSE,
same 4191 exchange sessions 2010-02-11 to 2026-10-09; NO synthetic QLD or TQQQ.
QQQ/TQQQ frozen source snapshot `bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129`.
2. Only TWO variants vs exact frozen whole-share baseline:
   - QLD-only at frozen 2x; leave 0,1.25,3 intact.
   - QLD-only at 2x, plus QQQ 75% / QLD 25% inside frozen 1.25x
     (instead of frozen QQQ 87.5% / TQQQ 12.5%).
   All target fractions multiply by original invested fraction 0.985.
3. Capital $100k no deposits, 2bps side fees, 10bps base/20bps adverse
slippage per trade side, lags 0 and 1 session. Trade at next observed adjusted
daily OPEN, mark daily CLOSE, whole-share cash-constrained ledger, no broker
fills or split timing. Exact original 8.0 NAV parity across all four stress
conditions is mandatory.
4. Historical RESEARCH-ONLY continuation hurdle: each of four lag/cost cases
must add >=0.50 percentage points CAGR **AND** worsen MaxDD no more than 1pp.
Include reused development 2010–2017, reused validation 2018–22 and later
2023–26; no new parameter tuning after results. A historically successful
screen still NEVER authorizes automated promotion or trading.
5. Source provenance limitation: Yahoo adjustments not independently cross-
audited, QLD daily objective is 2x of Nasdaq-100 (NOT guaranteed multi-day
2x); verify vendor prices and executable fills separately. No new clean OOS.
6. CI one bundled PR run and one research artifact with QLD snapshot and
human report. Keep PR draft until evidence read.

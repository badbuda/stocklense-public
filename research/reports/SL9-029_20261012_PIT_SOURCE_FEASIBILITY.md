# SL9-029 — PIT source feasibility, first-seen and executable quote audit (2026-10-12)

**Source-only findings.** This batch does NOT run a new return or drawdown
backtest and does not authorize any change to frozen StockLens 8.0.

## Independently observable external facts (checked 2026-10-12)

1. Official FRED ICE BofA HY OAS `BAMLH0A0HYM2` is daily **close**
   spread in percent. FRED explicitly states **from April 2026 only three
   years of observations**; ALFRED displays release-date range starting
   **2023-10-10**. This does not certify 2010–2022 as-of vintages or ICE
   rights for redistributed strategy research. The official FRED page
   showed latest **2026-10-08** observation, updated **2026-10-09**.
   Sources: https://fred.stlouisfed.org/series/BAMLH0A0HYM2 ;
   https://alfred.stlouisfed.org/series?seid=BAMLH0A0HYM2 .
2. FRED `series/vintagedates` records dates when a value changed/new
   value appeared, not an independently witnessed intraday vendor
   availability clock. Thus `realtime_start` cannot prove a strategy
   could use same-day ICE data before a trade.
   https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html
3. SEC official EDGAR guidance: some filings transmitted after 17:30 ET
   are disseminated next business day. `acceptanceDateTime` cannot
   be automatically treated as public first-seen or an M&A event.
   https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
4. No qualified licensed SIP NBBO quote stream or independent broker fill
   was connected to this GitHub batch. A JSON row saying `NBBO` is
   not independent proof. Prior Yahoo minute-bar OPEN is not a quote.

## Reproducible software artifacts (synthetic adversarial fixtures)

- `research_pit_credit_gate.py`: complete-response/series pin,
  2010–2022 *vintage* vs observation-date distinction, duplicate and
  impossible-date rejection, finite spread validation; returns BLOCKED
  even on well-formed metadata without independent permission/clock.
- `research_pit_event_gate.py`: SEC/GDELT metadata chronology, unique
  record IDs and scheduled FOMC/CPI future-result leakage rejection.
  Self-declared first-seen flags NEVER qualify.
- `research_pit_quote_gate.py`: XNYS and US DST opening-window,
  regular NBBO candidate bid/ask/size integrity, duplicate and crossed
  quote rejection. Self-declared fills NEVER qualify.
- Synthetic test fixtures only. No raw ICE series, news headlines,
  proprietary NBBO data, broker secrets, or historical ETF results added.

## Economic evidence / go-no-go

| Workstream | Independently qualified observations this batch | Result |
|---|---:|---|
| H1 ICE HY 2010–2026 legally usable, timestamp-certified PIT vintages | 0 | BLOCKED |
| D: SEC/GDELT independent first-seen + pre-release consensus | 0 | BLOCKED |
| A/H3: actual independent NBBO/fill receipts | 0 | BLOCKED |
| B: Excellence USD sweep/FX/margin terms | 0 | USER-OWNED, BLOCKED |
| E: independent immutable forward frozen8 paper pairs | 0 new | BLOCKED |

A passing test proves **parser behavior on fabricated fixtures only**.
No economic effect estimate, new alpha, new clean OOS or live trading claim
can be drawn from these counts. Existing frozen 8.0 historical proxy is
not a substitute for the missing evidence. The 63-session operational
checkpoint is not a guarantee of strategy profitability.

## Next strictly external evidence gates

Obtain authorized ICE or independently licensed comparable historical
credit vintages with timestamp and rights; separately timestamped
EDGAR/GDELT archived delivery plus pre-release consensus; genuine SIP
NBBO with conditions and broker execution receipts; independent WORM
forward source/time receipts. Never replace the predeclared H1 series
with a different macro series under the same hypothesis label.

### ALFRED intake envelope contract

Native FRED `fred/series/observations` JSON has no `series_id` field.
The offline parser therefore requires a local envelope of the form
`{"series_id":"BAMLH0A0HYM2","response":<unmodified API response>}`.
The envelope's ID is caller asserted and is **not** proof of the
underlying provider, original vendor publication clock or license.
The raw envelope SHA256 is an integrity checksum, not a signed receipt.

## 2026-10-13 amendment — separate curve/credit as-of source intake

A strict `research_pit_vintage_gate.py` now separately pins **T10Y3M**
(Treasury 10-year minus 3-month curve spread) and **BAMLH0A0HYM2**
(ICE high-yield OAS). It requires a complete FRED/ALFRED `output_type=1`,
`units=lin`, `file_type=json` single-day as-of response from before the
prospective trade date, with consistent row vintage windows, no pagination,
duplicate JSON keys, transformed values, future observations or fabricated
NaN. Missing values stay missing. The original credit shape gate now rejects
unwrapped native JSON; synthetic fixtures were corrected to the documented
pinned-envelope contract. Six new unittest methods include 15 adversarial
mutations. **These are shape tests, not independently witnessed first-seen.**

Official public pages inspected 2026-10-13:
- T10Y3M last displayed observation **0.99 percentage points** on
  **2026-10-09**, updated Oct 9 at 4:03 PM CDT.
  https://fred.stlouisfed.org/series/T10Y3M
- ICE HY OAS last displayed observation **3.15%** on **2026-10-08**,
  updated Oct 9 at 8:08 AM CDT; the page explicitly restricts
  FRED history to three years from April 2026 and ICE redistribution
  to internal use without written approval.
  https://fred.stlouisfed.org/series/BAMLH0A0HYM2
- The official API distinguishes as-of observations (`output_type=1`)
  from vintage-listing modes and defaults the real-time period to TODAY.
  https://fred.stlouisfed.org/docs/api/fred/series_observations.html

**Numeric evidence outcome:** 0 newly independently qualified as-of
historical trade-date observations, 0 independently timestamped SEC/GDELT
first-seen event rows, 0 actual licensed SIP NBBO/broker fills, 0 verified
Excellence USD sweep/FX/margin terms, 0 newly independently attested
forward 8.0 Paper pairs. The displayed latest FRED observations are
contemporary snapshots, NOT a historical PIT cohort. No alpha, CAGR,
MaxDD or fresh OOS was calculated; the mined 2010–2026 sample remains
reused. CI code success cannot establish economic qualification.

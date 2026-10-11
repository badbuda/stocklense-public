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

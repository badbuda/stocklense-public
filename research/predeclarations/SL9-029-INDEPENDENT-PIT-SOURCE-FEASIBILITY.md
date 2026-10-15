# SL9-029 — independent source feasibility / fail-closed intake (2026-10-12)

**Research evidence gate only; no new strategy candidate or historical alpha test.**
Registered before PR CI. Source-of-truth main 79ee3c7f76364681e1fbb062d2a661e236161c76.
Frozen 8.0 remains unchanged; observed QQQ/TQQQ are not re-simulated.
Never interpret metadata shape checks as independent historical first-seen,
vendor entitlement, real NBBO, broker execution, or OOS validation.

Five issue #61 streams: (A) validate only actual NBBO *candidate* quote
shapes, XNYS sessions, 09:30–09:33 America/New_York, bid/ask/sizes and
duplicate clocks; no independent SIP feed/fills. (B) Excellence actual cash
terms are user-owned; no EFFR substitution. (C) pin H1 to the exact ICE
BAMLH0A0HYM2 ALFRED series; require complete response, distinct observation
dates/vintages, no future observation, no duplicate or nonfinite spreads;
vintage DATE never proves intraday availability or license. (D) SEC EDGAR
acceptance is not dissemination, GDELT batch time not article first seen;
FOMC/CPI scheduled events must never contain actual result/surprise.
(E) no fresh forward WORM witness deployed or certified by these tests.

Official source findings before implementation:
- FRED/ALFRED ICE BofA HY OAS notes explicitly limit current FRED
  observations to three years from April 2026; ALFRED currently displays
  a 2023-10-10 release-date boundary, not qualified 2010–2022 first seen.
  https://fred.stlouisfed.org/series/BAMLH0A0HYM2
  https://alfred.stlouisfed.org/series?seid=BAMLH0A0HYM2
- ALFRED vintagedates are DATE revisions/new-value dates; no timestamp
  certification. https://fred.stlouisfed.org/docs/api/fred/series_vintagedates.html
- SEC filings transmitted after 17:30 ET may be disseminated next day,
  so acceptance time cannot be used as publication time.
  https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data
- SEC submissions API is a current snapshot; nightly bulk ZIP is not a
  historical first-delivery receipt.
  https://www.sec.gov/search-filings/edgar-application-programming-interfaces

One coherent draft PR, one automatic Fast Guard CI, adversarial synthetic
fixtures; no source downloading in CI, no keys, no unlicensed ICE bulk data
committed, no external WORM claim, no trading code touched.
**Stop rule:** source-qualification count remains 0 until actual
permissioned independent raw data and receipt checks exist.

### 2026-10-13 source-intake amendment (before this CI)

No trading hypothesis, threshold, or new backtest. Add strict single-as-of
FRED/ALFRED snapshot parser for two **noninterchangeable** series T10Y3M
and ICE BAMLH0A0HYM2. Use only synthetically generated fixtures for
adversarial parser checks; missing release-clock/rights/independent
capture continues to BLOCK any economic use. Do not infer 2010-2022
PIT history from an October 2026 FRED page.

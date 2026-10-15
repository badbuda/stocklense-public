# SL9-030 — Causal calendar source audit (2026-10-15)

## Measured calendar result

Actual deterministic calculation using pinned exchange-calendars XNYS and pandas USFederalHolidayCalendar: **251 XNYS sessions** in 2026, **11 observed federal holidays**, and **2 dates that overlap**: **2026-10-12** (Columbus Day) and **2026-11-11** (Veterans Day). Rate: **2/251 = 0.7968%**. This is a calendar mismatch, not a measured strategy return or proof of missed SEC/FRED publications.

Under the SEC's published rule, a non-exception **8-K transmission beginning Friday 2026-10-09 at 17:31 ET** cannot be assumed publicly disseminated that Friday; the next US federal business-day proxy is **Tuesday 2026-10-13**, despite NYSE trading on Monday October 12. An exception **Form 4** can potentially be disseminated on Friday before 22:00 ET, but only an independent public-receipt timestamp can certify actual first-seen. A Friday 18:00 ET receipt precedes the next regular XNYS open on Monday October 12 at 09:30 ET, yet does not imply the SEC or FRED published anything that Monday.

New code research_cross_calendar_gate.py and 17 local adversarial pytest cases enforce the SEC cutoff, exceptions, acceptance chronology, US DST and strict next XNYS open. Reproducible JSON is research/results/sl9_030_cross_calendar_2026.json. Tests use synthetic clocks, not historical SEC receipt data. US federal holidays are only a conservative proxy, not an independently authenticated full EDGAR schedule.

## Five workstream evidence gates (issue #61)

| Workstream | Newly qualified real evidence |
|---|---:|
| A — independently licensed NBBO and actual broker fills | 0 |
| B — verified Excellence cash sweep, USD financing, FX/commission terms | 0 |
| C — historically licensed ALFRED/FRED/ICE vintages with independent first-seen | 0 |
| D — SEC/GDELT external first-seen and pre-release consensus | 0 |
| E — new externally attested immutable StockLens 8.0 Paper pairs | 0 |

No backtest was run, no return or drawdown improvement established, no new clean OOS, no synthetic TQQQ, no frozen 8.0 change, no broker trading. Reject a one-calendar join as causally unsafe. This source research does **not** fix the separate AWS journal outage in Draft PR #80.

Official documentation:
- https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/determine-status-my-filing
- https://www.nyse.com/trade/hours-calendars
- https://www.opm.gov/policy-data-oversight/pay-leave/federal-holidays/
- https://fred.stlouisfed.org/docs/api/fred/realtime_period.html

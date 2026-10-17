# SL9-032 — provenance integrity findings and blockers, 2026-10-17

## Code finding

Before this change, the offline SEC/GDELT, candidate NBBO and ICE-credit
parsers used Python's default JSON decoding, which silently accepts
duplicate keys and nonstandard nonfinite numbers. Such raw inputs are
not safe evidence envelopes. The new shared strict decoder rejects
duplicate keys, NaN/Infinity, float overflow and invalid UTF-8.
The SEC event gate additionally rejects claimed publication before
acceptance; the credit vintage gate rejects overlapping closed
revision intervals for one observation. Existing ALFRED as-of snapshot
code already had strict duplicate-key checking.

A deterministic 12-case adversarial synthetic regression suite is
included. The GitHub CI XML artifact, not this report, is the
authoritative record of executed test counts and pass/fail outcomes.
These checks do NOT authenticate source ownership or actual public
first-seen timestamps.

## Issue #61 evidence gates: newly independently qualified rows

A. Actual 09:31 SIP NBBO + broker fills: **0**.
B. Actual Excellence USD cash/FX/financing terms: **0**.
C. Historical as-of ALFRED curve + licensed ICE credit with release clock: **0**.
D. Independently timestamped SEC/GDELT and consensus cohort: **0**.
E. New independently attested immutable 8.0 forward Paper pairs: **0**.

No return or MaxDD was recomputed. No fresh OOS or alpha claim.
PR #62 real Cboe VIX guards were already rejected (0/4 cases).
Frozen 8.0, actual QQQ/TQQQ-only return policy, and broker-disable
constraints remain unchanged.

Official source constraints:
- https://fred.stlouisfed.org/docs/api/fred/realtime_period.html
- https://www.sec.gov/submit-filings/filer-support-resources/how-do-i-guides/determine-status-my-filing

Production recovery is separate. Main remained 79ee3c7 on this cut;
2026-10-16 AWS export run 38915134774 and audit run 38913993346
both failed and are NOT independent prospective Paper receipts.

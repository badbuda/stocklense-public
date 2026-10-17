# SL9-032 — source JSON integrity predeclaration, 2026-10-17

Scope: offline SEC/GDELT, candidate NBBO and ICE-credit vintage parsers in draft PR #77.
Parent main SHA: 79ee3c7f76364681e1fbb062d2a661e236161c76.
No new market data, economic hypothesis, trading decision or return backtest.

Hypothesis: default JSON parsing can silently accept duplicate source keys,
NaN/Infinity or overflowed numeric tokens. This can hide contradictory
source IDs, quote prices or vintage values before any provenance audit.
Additional invariants: SEC filing publication cannot precede acceptance;
ALFRED closed realtime ranges for the same observation cannot overlap.

Preregistered synthetic adversarial regressions: 9 JSON parser mutations
(3 duplicate, 3 nonfinite constants, 3 float overflow), 1 SEC chronology,
1 overlapping credit vintage, 1 invalid UTF-8 = 12 tests. All must fail
closed. Existing valid-fixture tests must continue to pass.

Passing proves only parser correctness. It cannot establish ALFRED
intraday availability, ICE redistribution rights, independently archived
SEC/GDELT first-seen, real SIP NBBO, Excellence broker cash/FX terms or
externally immutable StockLens 8.0 Paper receipts. All five issue #61
evidence gates remain blocked without genuine new sources. No synthetic
TQQQ, no promotion, no VIX/EWMA/ML/QLD/GLD/TLT rerun on mined history.

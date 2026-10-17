# SL9-033 — preregistration, 2026-10-18

Parent: SL9-032 strict JSON; stacked on draft PR #77. Reviewed main: 4bacd94359768669895a72621214d51d568d809b.

Hypothesis: a pair of individually valid ALFRED as-of snapshots can still be compared incorrectly when vintage order is reversed, historical rows disappear, numeric spellings differ, or missing observations become available. These are *data-integrity* hypotheses, not trading hypotheses.

Frozen synthetic fixtures: earlier 2026-10-13 (2 rows), later 2026-10-14 (3 rows), hypothetical 2026-10-15 decision, T10Y3M. Expected: one numeric revision, one missing-value fill, one new observation. Adversarial: reversed vintage, removed row, future as-of, equivalent decimal spelling. All untrusted inputs must fail closed.

No historical return test, no independent first-seen, no ICE license, no broker action or strategy promotion. Retain draft until CI and artifacts reviewed. PR #62 Cboe VIX negative remains closed.

# SL9-031 — code and research coverage

The new research_pit_decision_join.py rejects pre-trade source-clock
violations for FRED/ALFRED, SEC and GDELT, and evaluates only displayed
NBBO candidate size. It never treats claimed provenance as proof.
The SEC exception list now includes official form S-BMEF.

Issue #61 evidence gates A through E remain blocked:
actual NBBO/fills, broker-specific cash/FX terms, historical
licensed vintage clocks, independently received news, and
external immutable frozen8 Paper receipts. No new alpha or OOS.

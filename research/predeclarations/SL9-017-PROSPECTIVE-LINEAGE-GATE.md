# SL9-017 — Forward paper evidence fingerprint drift is not CURRENT
2026-10-11. Research/Paper audit only. Frozen 8.0 and any broker execution unchanged.

Observed immutable registry says definition_matches_registration=true but fingerprint_matches_registration=false for SL9-007. The former means experiment definition remains same; the latter is evidence fingerprint drift, potentially legitimate after price/source updates but requiring independent traceability review. Previous freshness audit silently did not surface either flag. New gate: a mismatched definition => BLOCKED; evidence drift => ATTENTION (never falsely "CURRENT"); missing evidence attestation => ATTENTION. No mutation of fingerprint histories; no backfill, no broker trades, no research alpha.

Green CI tests demonstrate report semantics only. Review actual lineage to determine benign provenance update vs substantive prospective evidence change; do not treat this administrative flag as a backtest performance failure.

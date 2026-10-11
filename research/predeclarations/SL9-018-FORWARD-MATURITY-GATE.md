# SL9-018 — reconcile maturity / freshness and forward evidence integrity

Date 2026-10-11. No algorithm changes, no live orders, no signal/price rewriting.

**Observed source issue:** SL9-007 queue fingerprint (995ffc17…) differs from preregistered evidence fingerprint (ffd63bf…), while registered experiment *definition* fingerprint remains equal. Evidence mismatch is visible from registry commits 2026-10-09 and 2026-10-10, and must not be promoted to a false positive maturity PASS. We do NOT claim it proves tampering: the dataset can refresh legitimately. Require independent same-source fingerprint reconciliation and preserved receipt before accrediting any new forward evidence.

Previous `prospective_maturity.py` shows `evidence_fingerprint_current=false` but the same row can still have `evidence_state=ACCUMULATING_FORWARD_EVIDENCE` and top PASS. This patch makes:
- Changed experiment definition or missing source-audit evidence => BLOCKED.
- Changed data evidence fingerprint, unchanged definition => ATTENTION, no silent PASS.
- Missing/changed persisted row counts => BLOCKED.
- Matched fingerprint + completed sessions => accruing, not validated alpha.
- Historic source dates strictly after inception do not prove first-seen provider availability, real broker fills or untouched OOS by themselves.
- Keep original StockLens 8.0, weights and all execution paths untouched. Test fixtures are synthetically constructed for validation only.

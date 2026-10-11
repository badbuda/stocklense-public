# SL9-025 — fail-closed legacy paper maturity after concurrent SL9-024 merge
On 2026-10-11 the independently green SL9-024 contract PR #70 merged
while a second branch #71 was under CI. Carry over only unique safety fixes
rather than merging two competing contract scripts:
- Legacy paper/challenger row counts NEVER automatically authorize
  forward performance claims, even at 252 or 500 days.
- Legacy SL9-007 synthetic QQQ*exposure rows cannot qualify frozen8 real ETF
  signed external server receipts.
- Local receipt JSON cannot authorize capital, execution or independent
  provenance merely by adding a true flag; reject it.
- Keep PR #70's own single frozen forward contract and all its tests.
- Frozen 8.0 untouched. External WORM storage and real NBBO/fills not deployed.

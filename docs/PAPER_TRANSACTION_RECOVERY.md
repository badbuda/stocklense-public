# Paper Trading B3 crash-recovery contract

Fixed: paper_portfolio.reconcile used to append N trades, append the ledger row, overwrite state.json, and overwrite latest.md separately. A process killed between these operations could leave local files inconsistent and make the next attempt fail as DUPLICATE_PAPER_SESSION.

Implemented:
- Build all prospective modeled receipts from the prior frozen signal and observed QQQ/TQQQ minute bars FIRST.
- Write a durable per-session prepare record, including exact UTF-8 destination bytes and their SHA256 digests, under paper_portfolio/.transactions/YYYY-MM-DD.json.
- Replace trades, ledger, state and latest markdown individually with temp-file + fsync + os.replace on the same filesystem.
- On local rerun, inspect the pending record BEFORE recomputing prices or placing modeled trades. Finish ONLY the exact prepared bytes if each destination matches its prepared BEFORE or AFTER hash; reject divergence and tampering.
- Remove the prepare record only after all destinations match the prepared digest; a crash on this step can be replayed idempotently. CSV schemas can extend with new fields without losing older rows.
- Hard-fail with an explicit error for corrupt/incomplete manifests or inconsistent external writes; no retroactive paper fills, and no broker trading permissions.

IMPORTANT ENVIRONMENT LIMITATION: GitHub Actions runners are disposable. A crash before the workflow's final Git commit means the local prepare and partial file writes are NOT published at all, so a new job cannot find that local prepare. GitHub publishes generated artifacts in ONE remote git commit after end-of-job validation. This is an all-or-nothing REPOSITORY PUBLICATION, NOT guaranteed retention of an uncommitted simulated fill. The missed session still must be recorded as a gap; do not reconstruct historical fills. Proper independent durable journaling requires a future AWS write-ahead append-only store/transaction.

No strategy calculation was modified. Existing paper model is still observed Yahoo minute-bar reference prices plus MODELLED costs, not broker execution.


## B6 bounded AWS publication (2026-10-09)
- The same recoverable local transaction now optionally publishes `paper_portfolio/latest_session.json` with schema v1, the exact forward session row and trades, and explicit `broker_fills_observed=false`. The published snapshot is atomic with CSV/state/latest and is covered by the prepare record.
- The AWS paper-evidence inline Lambda now fetches this small fixed-size receipt instead of nonexistent `lg.csv` / `trs.csv` paths and eventually unbounded cumulative ledger/trades files. It checks trading date, the prior pre-open frozen signal, modeled source, matching weights, trade count, execution windows and conditional DynamoDB idempotence.
- The existing cumulative ledger remains available for local audits but does not need to fit in one Lambda HTTP response. Latest-only receipt is intentionally NOT a durable, independently attested historical archive; DynamoDB remains the per-session archive. Source is still mutable GitHub main and NOT an independent vendor feed.
- Deployment gate: this changes `infra/aws/paper-signal-journal.yaml` and MUST be applied by an explicitly reviewed CloudFormation UPDATE on the existing `stocklens-paper` stack in `eu-central-1`. CI green tests source behavior only; no AWS update or SNS confirmation can be inferred.
- B4/B5 and production-readiness remain open: historical adjusted-price reproducibility/independent quote validation, broker bid/ask and fills, calendar-aware missing-invocation alarm, and sufficient prospective samples. No live capital authorized.

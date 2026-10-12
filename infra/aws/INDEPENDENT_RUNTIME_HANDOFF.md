# AWS-independent runtime handoff — staged, no production change

Status: **NOT DEPLOYED / BLOCKED**. Frozen StockLens 8.0 remains shadow-only; no broker actions.

## Verified from deployed CloudShell evidence (2026-10-12)

- `stocklens-paper-shadow` fetches `main/shadow_history/latest.json` from `raw.githubusercontent.com`.
- `stocklens-paper-paper-evidence` fetches `docs/paper_portfolio_integrity.json`, `paper_portfolio/latest_session.json`, `shadow_history/latest.json`, and a date-keyed prior signal from the same GitHub host.
- CloudFormation schedules AWS archival at 09:10/09:20 UTC Tue–Sat; this processes the **previous** New York session after a GitHub producer. Do not simply move cron times.
- Two Shadow and two Paper archive entries were observed for 2026-10-08/09. These are not proof of self-sufficient production or SHA-content integrity.
- `stocklens/core.py` and `stocklens/shadow.py` contain the frozen decision replay; `stocklens/data.py` downloads adjusted QQQ history from yfinance; paper execution depends on actual observed intraday prices. Do not replace with synthetic TQQQ.
- Watchdog heartbeat measures **invocation**, not successful business validation.

## Migration gates

1. **Inventory and freeze:** capture deployed Lambda CodeSha256, CloudFormation template/change set, DynamoDB read-only snapshot, 8.0 source commit, and exact input/receipt hashes. Run `python infra/aws/runtime_dependency_audit.py` in CloudShell. No secrets in reports.
2. **Independent market-data ingestion:** AWS producer obtains **observed** adjusted QQQ closes and real QQQ/TQQQ intraday execution prices from a documented provider. Store immutable date-keyed raw payloads, retrieval timestamps, provider metadata and SHA-256 in versioned private S3. Fail closed on missing, late, incomplete, revised or ambiguous market data. Never treat a GitHub-mirrored file as independent.
3. **Frozen decision compute:** package the exact `stocklens/core.py` replay and `stocklens/shadow.py` report semantics into a pinned Lambda image or ECS task. Read versioned S3 input; write immutable session-scoped signal plus manifest; reject divergence on replay. Run side-by-side with production; no auto-promotion.
4. **Paper compute:** package the exact `paper_portfolio.py`/accounting code and dependencies. Use real observed execution receipts; write immutable session-scoped paper result and integrity report to S3. Preserve no-broker-fills and no-orders flags. If no observed execution data, mark session BLOCKED, not success.
5. **Read-side cutover:** in a **separate** reviewed CloudFormation change, grant S3 GetObject only for scoped prefixes and replace GitHub HTTP reads with S3 immutable version IDs. Verify matching content hashes and output equivalence for 2026-10-08/09 and a new completed session. Do not overwrite the retained DynamoDB table or change trading mode.
6. **Scheduling and monitoring:** trigger AWS producer after verified completed US session, then gate Shadow/Paper on producer success; ensure NYSE holiday and DST handling. Emit separate success/completeness metrics, alert on absent or invalid receipts, and test SNS delivery. Heartbeat invocation alone is insufficient.
7. **Rollback:** retain previous Lambda versions/aliases, CloudFormation change set and previous S3 object versions; do not delete historic DynamoDB rows. Abort on mismatch, restore old alias without writing divergent records.
8. **Acceptance:** turn off GitHub Actions **in a controlled test**; confirm AWS produces new QQQ input, frozen signal, actual-price Paper evidence, matching hashes, complete alerts, dashboard updates and replay-safe writes over multiple real completed market sessions. Until then independence is **NOT PROVEN**.

## Explicit no-go

No direct modification of live Lambda or EventBridge from this branch. No source URLs containing credentials. No brokerage integration. No synthetic prices. No new alpha research, no optimizer, and no strategy change. The static dependency audit cannot prove that all upstream data generation has migrated.

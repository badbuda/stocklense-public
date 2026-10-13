# AWS-independent runtime handoff — staged, no production change

Status as of 2026-10-13: **INDEPENDENT STAGING DEPLOYED; SIGNAL ACCEPTED; LIVE PRODUCTION CUTOVER BLOCKED**. The 2026-10-12 completed-session Signal was archived in private versioned staging S3 with an AWS-side verified SHA/version receipt (4,724 QQQ rows, level 3, leverage target 3x, action NO_CHANGE). Four Lambda import smokes passed; the combined Signal+Paper orchestrator remains DISABLED and the account-wide $20 budget is alert-only. No broker orders or production `stocklens-paper` changes.

**Important deployment boundary:** the newest Draft PR #78 research/staging code, including the signal-silence watchdog and proposed Paper preflight, is NOT proven deployed until the operator reapplies the pinned CloudFormation+ZIP and verifies the Lambda imports. The prior CloudShell deploy reported `STAGING_SNS_EMAIL_UNCONFIRMED`, so Signal-only automatic scheduling has NOT been confirmed enabled. SNS actual end-to-end email delivery is not proven.

**Independent source parity still FAILED**: 25 direct Yahoo Chart prices were outside the configured 8-binary32-ULP tolerance despite matched 4,303 policy decisions; second-provider evidence is not proven. The paper preflight (when deployed) will only estimate observed-minute-bar modelled fills, not broker fills, and NEVER create the actual Paper book or authorize bootstrap.

## Verified from deployed CloudShell evidence (2026-10-12)

- `stocklens-paper-shadow` fetches `main/shadow_history/latest.json` from `raw.githubusercontent.com`.
- `stocklens-paper-paper-evidence` fetches `docs/paper_portfolio_integrity.json`, `paper_portfolio/latest_session.json`, `shadow_history/latest.json`, and a date-keyed prior signal from the same GitHub host.
- CloudFormation schedules AWS archival at 09:10/09:20 UTC Tue–Sat; this processes the **previous** New York session after a GitHub producer. Do not simply move cron times.
- Two Shadow and two Paper archive entries were observed for 2026-10-08/09. These are not proof of self-sufficient production or SHA-content integrity.
- `stocklens/core.py` and `stocklens/shadow.py` contain the frozen decision replay; `stocklens/data.py` downloads adjusted QQQ history from yfinance; paper execution depends on actual observed intraday prices. Do not replace with synthetic TQQQ.
- Watchdog heartbeat measures **invocation**, not successful business validation.

## Read-only first Paper acceptance (staging only; new code NOT yet deployed)

The first Paper **preflight** must use a separate `CandidatePaperPreflightLambda`
(`infra.aws.independent_paper.preflight_handler`) and IAM
`CandidatePaperPreflightRole`. This role can read only the required prefixes
of the **private staging S3 bucket** and write its own bounded CloudWatch logs.
It has **no S3 PutObject, Lambda InvokeFunction, SNS Publish or broker permission**.
The writable `CandidatePaperLambda` does not accept preflight mode.

After a separately verified completed session and immutable daily signals,
the operator can run `bash infra/aws/accept_independent_paper_preflight.sh
YYYY-MM-DD` between that NYSE session's close and the NEXT NYSE session open.
It refuses a Paper genesis, predecessor/current continuity, or partial existing
Paper/market objects; checks actual S3 server timestamps and computes an audited
modelled Paper result from observed QQQ/TQQQ 1-minute prices. It does **not**
create a first Paper receipt, make any model-ledger entry, or authorize a real
Paper bootstrap. Always verify the five import-only AWS Lambda smoke results,
including `paper_preflight`, after deploying the pinned code.

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

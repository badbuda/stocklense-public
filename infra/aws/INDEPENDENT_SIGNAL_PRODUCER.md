# AWS-independent StockLens 8.0 candidate — operational handoff

**Draft only, not deployed. Does NOT change the existing stocklens-paper stack or send broker orders.**

## What is implemented

- `independent_market_ingest.py`: obtains QQQ **observed adjusted daily closes** from the Yahoo chart endpoint *from within AWS*, not from a GitHub artifact. Vendor response is bounded and checked for correct symbol, timezone, completed session, positive finite closes, ordering, and minimum pre-2009 warmup. This is **one data provider** and its history may be revised or unavailable; independent cross-vendor price parity remains unproven.
- `independent_signal_producer.py`: invokes **unchanged** `stocklens/core.py` frozen state replay; rejects malformed dates, invalid prices and incorrect sessions; carries 253-session SHA-256 fingerprint and a shadow-only execution flag. Its standalone Lambda handler requires versioned S3 data + manifest; the integrated candidate invokes its pure `build_signal` directly.
- `independent_pipeline.py`: connects Yahoo -> immutable date-keyed, versioned private S3 market snapshot -> manifest -> StockLens 8.0 signal -> immutable signal snapshot. Repeated identical requests are checked; divergent overwrites fail closed. Writes **only** to its staging S3 bucket. **No DynamoDB, broker, GitHub or mutable latest pointer.**
- `independent-staging.yaml`: a **separate** stack with an encrypted, versioned, private S3 bucket; manually-invoked Lambda and least-privilege logs/S3 role. No EventBridge rule, no shared DynamoDB or IAM broker grants.
- `deploy_independent_staging.sh`: one local packaging+deployment command from a clean checked-out repository. Creates a separate encrypted/private artifact bucket and the staged CloudFormation stack. It does not invoke the function. AWS permissions and service costs apply.
- `verify_independent_candidate.py`: read-only checks the S3 market, manifest, signal versions, SHA chains and no-broker flags.

## Single batch to stage in AWS (do NOT run before CI green and review)

From a clean checkout of the specific reviewed PR commit, in AWS CloudShell in **eu-central-1**:

```bash
bash infra/aws/deploy_independent_staging.sh
```

Review the CloudFormation change and AWS costs first. The command creates **new isolated resources**, not updates to the production `stocklens-paper` stack. It packages only the candidate modules and unchanged frozen `stocklens/core.py`. Repo/GitHub is needed **at build time**, not at Lambda runtime.

Once an actual US market session has completed **after 18:00 America/New_York** and vendor data is available, manual staging example (fill SESSION with that completed NY trading date):

```bash
SESSION=YYYY-MM-DD
aws lambda invoke --region eu-central-1 \
  --function-name stocklens-independent-staging-candidate \
  --cli-binary-format raw-in-base64-out \
  --payload "{\"mode\":\"STAGING_ONLY\",\"expected_session\":\"$SESSION\"}" \
  /tmp/stocklens-staging-invocation.json
cat /tmp/stocklens-staging-invocation.json
python3 infra/aws/verify_independent_candidate.py "$SESSION"
```

A Lambda invocation may have `FunctionError` even if AWS CLI exited 0; inspect the invocation payload and CloudWatch logs before accepting a candidate. A successful staging receipt demonstrates **internal consistency**, not independent vendor parity or an AWS-only paper ledger.

## Blockers before any automated production cutover

1. **Identical-source parity:** prove adjusted Yahoo chart prices against frozen yfinance `auto_adjust=True` on identical timestamps and compare decisions, feature-window hash, action, levels and weights for historical regimes and fresh actual completed sessions. Candidate and historical snapshots may have data revisions. **Do not compare generated_at_utc or source labels as if identical.**
2. **Observed paper executor:** migrate the exact `stocklens.paper` modeled ledger and independent `paper_portfolio_integrity` checks. Use observed 09:31/09:32 QQQ/TQQQ one-minute raw prices, actual closing bars and corporate actions. Persist prior state and previous valid signal in immutable versioned S3. No retrospective fills or synthetic leveraged ETF history.
3. **Calendar, scheduling and health:** XNYS-aware gating for holidays, half-days, US DST, provider outages, freshness and missing-session alerts; only enable schedules after end-to-end evidence. Current 09:10/09:20 UTC archive clocks depend on GitHub and should not be reused blindly.
4. **Safe release:** side-by-side compare paper NAV, fees, positions, receipts and hashes for multiple genuinely completed sessions; inspect IAM+S3 versions, test failure paths and SNS; reviewed, reversible aliases/CloudFormation change set. Never overwrite the existing retained DynamoDB table.
5. **GitHub-off test:** stop GitHub publisher only after AWS produces and archives both the signal and actual-price paper independently for multiple sessions. Status remains **BLOCKED** until successful.

## Failure semantics

- Provider 404, 429, bad timestamps, missing adjusted prices, weekend bars, stale session or blank input -> **fail**, never fabricate.
- Existing immutable content with a different byte digest -> **divergence error**, never overwrite.
- Yahoo as the single source -> mark provider parity *unproven*.
- No broker calls, no actual fills, no financial order authorization.

## Cost and access

This stack can incur Lambda, S3, IAM-related and CloudWatch charges; the data bucket has `DeletionPolicy: Retain` and survives stack deletion. An account owner must review stack changes and verify root MFA, budgets and least privilege. The public repo never contains AWS secrets.

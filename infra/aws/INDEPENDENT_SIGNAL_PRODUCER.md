# AWS standalone runtime candidate — combined signal + modeled Paper

**Status: isolated Draft, not deployed to AWS, not a replacement of `stocklens-paper`.**

This change packages two candidate Lambda functions in a **new** stack `stocklens-independent-staging`, and a private versioned S3 bucket. Neither Lambda reads GitHub at runtime, submits broker orders, updates the current DynamoDB archive, or has a production scheduler.

### Provenance and frozen economics

**Signal candidate** calls the public Yahoo chart API from AWS, obtains observed **adjusted daily QQQ closes** with explicit session, schema, timezone and SHA checks, replays unchanged `stocklens/core.py` 8.0 state and stores `market/qqq/YYYY-MM-DD.csv`, `manifests/qqq/YYYY-MM-DD.json`, `signals/YYYY-MM-DD.json` in private, versioned S3. `independent_signal_producer.py` includes a standalone S3-backed entry point; the integrated candidate runs `independent_pipeline.handler`.

**Paper candidate** reuses the **unchanged** `stocklens.paper` observed raw minute-price importer, fees/slippage, rebalance and accounting functions, plus the existing independent `paper_portfolio_integrity.evaluate` audit. It fetches live Yahoo market data via pinned yfinance **inside AWS**, not from GitHub. It requires the previous completed XNYS session's signal to have been generated before today's NY market open. It stores immutable `market/paper/YYYY-MM-DD.json` and `paper/sessions/YYYY-MM-DD.json` receipts, with a prior-receipt SHA chain, cumulative state/history, verified cash and share inventory, observed QQQ/TQQQ bar opens, dividends/splits, and no broker actions. Vendor HTTP byte-streams are **NOT** yet archived: the market receipt stores the validated normalized observation, its source tag and SHA, not independent quote provenance. Be accurate about this in later production readiness claims.

Both candidates **fail closed** on missing days, late signals, unexpected prices, invalid corporate actions, divergent immutable objects and unsuccessful accounting verification.

### Important account continuity distinction

This is a **new independent staging paper book**. The first receipt uses a *deliberate, explicit prospective* `bootstrap:true` and a new modeled starting value of $100,000; this is NOT a migration or replacement of the existing `stocklens-paper` ledger. There is no automatic backfill, inferred historic executions or silent transfer of the existing holdings. A future production cutover must separately import and verify the existing book/state/ledger with hashes or explicitly approve a new book.

### One packaging + staging deployment

Run only from a **clean checked-out reviewed commit**, with AWS owner approval and a billing budget, in Frankfurt `eu-central-1`. The command uses Python 3.12, pip, native wheels and AWS IAM rights, and **creates billable resources**:

```bash
bash infra/aws/deploy_independent_staging.sh
```

It packages the frozen modules and all pinned requirements, enforces the uncompressed Lambda size limit, stages the ZIP by its SHA and commit, then deploys the separate CloudFormation stack. Missing Python 3.12, oversized package, bad CloudFormation or IAM permission aborts. No stack under the name `stocklens-paper` is changed.

### Prospective two-session acceptance (NOT historical replay)

After a *genuinely completed* NYSE session and after at least 18:00 New York local time, run candidate Signal once for that date, e.g. replacing `YYYY-MM-DD`:

```bash
SESSION=YYYY-MM-DD
aws lambda invoke --region eu-central-1 \
  --function-name stocklens-independent-staging-candidate \
  --cli-binary-format raw-in-base64-out \
  --payload "{\"mode\":\"STAGING_ONLY\",\"expected_session\":\"$SESSION\"}" \
  /tmp/stocklens-candidate-signal.json
cat /tmp/stocklens-candidate-signal.json
python3 infra/aws/verify_independent_candidate.py "$SESSION"
```

Ensure the invocation response contains **no FunctionError** before marking a success. Once the *next actual XNYS trading session* has closed, produce that day's Signal. Only now, with a valid prior signal that existed before today's open, start the **new staging** Paper book:

```bash
SESSION=YYYY-MM-DD   # SECOND genuinely completed XNYS session
aws lambda invoke --region eu-central-1 \
  --function-name stocklens-independent-staging-paper-candidate \
  --cli-binary-format raw-in-base64-out \
  --payload "{\"mode\":\"STAGING_PAPER_ONLY\",\"expected_session\":\"$SESSION\",\"bootstrap\":true}" \
  /tmp/stocklens-candidate-paper.json
cat /tmp/stocklens-candidate-paper.json
python3 infra/aws/verify_independent_paper.py "$SESSION"
```

On *subsequent* completed XNYS sessions, produce each Signal and Paper with `bootstrap:false` (or omit the flag). Any missed modeled session must be recorded as a gap, never backfilled or treated as a broker fill. The Paper pipeline fetches Yahoo's short-lived 1-minute market data; delayed invocations may be unexecutable, by design.

### Before any production activation

1. **Parity:** match Yahoo chart adjusted history to the original pinned yfinance series on same session and revision; compare frozen output with the original generator including 253-session hash, levels, actions, targets and previous state. Same-day timestamp differences are expected; semantic parity must be demonstrated rather than asserted.
2. **Real provider evidence:** store byte-level 1-minute vendor responses, retrieval times, corporate-action provenance, and independent vendor comparison. Normalized receipts alone do not prove quote/executable market quality. Prove provider robustness through outages and revisions.
3. **Continuity:** reconstruct/import the existing modeled Paper history and inventory if migrating it, or explicitly approve a separate new book. Verify complete independent accounting and cross-session model parity.
4. **Scheduling and monitoring:** incorporate DST, XNYS calendar and half-day checks; enforce producer-before-consumer ordering, atomic incident signaling, missing-session metrics and SNS delivery. A heartbeat that only counts invocations is insufficient.
5. **Controlled runtime test:** new signals **and** modeled paper receipts for multiple prospective sessions with GitHub Actions intentionally off, independently verified S3 and no broker privileges; rollback plan and alerts tested.

Until those gates are green the existing `stocklens-paper` Lambdas must remain untouched, and the new PR stays Draft.


### Disabled automatic orchestration (code staged, NOT activated)

A third AWS candidate Lambda `independent_orchestrator.py` is included. Its
EventBridge rule is intentionally `State: DISABLED`. If later approved,
the rule is scheduled at `00:10 UTC Tue-Sat`, which is after **18:00 ET**
on the preceding US market date across daylight saving changes. The
orchestrator independently checks the NYSE XNYS session calendar, skips
exchange holidays, and synchronously invokes Signal **before** Paper. It
never bootstraps a portfolio, never issues broker orders, and fails closed
when a candidate Lambda fails or reports an invalid receipt.

Do **NOT** enable this rule until the model, market-data source and Paper
continuity gates above are proven for multiple completed real sessions
and a human has approved the separate staging book. The existing production
archive schedule continues to read GitHub and is not modified by this PR.

Retries for unchanged QQQ prices now reuse the **original manifest retrieval
timestamp**, preserve the first signal's timestamp and S3 object version,
and verify the immutable bytes. Real changes in historical adjusted prices
still trigger a fatal divergence instead of silently rewriting receipts.

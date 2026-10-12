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

Run only from a **clean checked-out reviewed commit**, with AWS owner approval and a billing budget, in Frankfurt `eu-central-1`. The command uses the available CloudShell `python3` (3.9 or newer) to download **CPython 3.12 / Amazon Linux compatible x86_64 wheels** using pip's cross-target flags. A local `python3.12` executable is **not required**. The Lambda runtime itself remains Python 3.12. Pip, native wheels, and AWS IAM rights are required, and **the deployment creates potentially billable resources**. Packaging and CloudFormation template validation run before creating AWS resources:

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


### CloudShell workaround recorded October 12, 2026

An earlier deployment script exited with `Python 3.12 is required to package the candidate's native wheels` after cloning the repository. That was a **packaging-tool prerequisite error**, not a failure of either candidate Lambda or AWS itself. The updated branch builds Lambda-compatible CPython 3.12 wheels using the installed `python3`, validates package size and extension ABI, validates CloudFormation, and only then creates or updates isolated staging resources. After `git pull --ff-only` from the branch clone, rerun `bash infra/aws/deploy_independent_staging.sh`. Never install a random Python binary or change the Lambda runtime to match CloudShell just to satisfy the former script.

A partially started earlier invocation may have created a private S3 artifact bucket before aborting; the new script reuses that bucket safely, without touching the existing `stocklens-paper` deployment. AWS costs and IAM rights still apply. If a platform-specific wheel does not exist, the new binary-only resolver **fails closed** rather than building a possibly incompatible CloudShell native binary.


### October 12 CloudFormation quota fix (isolated staging only)

Observed staging deployment failure: `CandidateLambda` and `CandidatePaperLambda` returned
`Specified ReservedConcurrentExecutions for function decreases account's UnreservedConcurrentExecution below its minimum value of [10]`.
No defect in the frozen trading model was established by this CloudFormation failure.

This branch now removes `ReservedConcurrentExecutions: 1` from **all three candidate Lambdas**.
The account-wide AWS concurrency limit remains in effect and the candidate EventBridge schedule is **DISABLED**.
No concurrency quota increase, reserved allocation, broker privileges or `stocklens-paper` changes are requested.
Warning: lack of reserved concurrency also means the Lambdas share normal unreserved concurrency,
so the enabled schedule and automatic retries must NOT be approved before operational safeguards.

A failed first-time CloudFormation creation usually ends in `ROLLBACK_COMPLETE`;
such a stack cannot be updated. To avoid asking for multiple manual commands, the staging
script supports **explicit one-time cleanup of only the exact isolated, rolled-back staging stack**:

```bash
git pull --ff-only &&
STOCKLENS_RECREATE_ROLLED_BACK_STAGING=1 bash infra/aws/deploy_independent_staging.sh
```

The opt-in deletion is permitted only when the AWS-reported stack status is exactly
`ROLLBACK_COMPLETE`, the CloudFormation description equals this candidate template's description
and the stack ARN matches the current account, region and fixed staging name. No other
CloudFormation status or stack may be deleted. No deletion is attempted without the opt-in flag.
If the delete fails, the script stops and prints the CloudFormation event reasons.
The existing production `stocklens-paper` stack is untouched.

**Retained S3 note:** `CandidateData` has `DeletionPolicy: Retain`. If the first
failed creation got far enough to make this bucket, the old bucket may remain after
the stack is deleted and could incur charges. This opt-in path intentionally does not
automatically delete any S3 objects/buckets; inspect and clean up only with explicit
authorization after determining whether it contains evidence.


### October 12 staging deployment success and first runtime smoke gate

The account owner confirmed `CREATE_COMPLETE` for `stocklens-independent-staging`,
including Signal, Paper, Orchestrator Lambdas, one private S3 data bucket and a
disabled EventBridge schedule. This confirms **CloudFormation provisioning**, not
runtime import integrity or real data-source / accounting parity.

Three staging handlers now recognize a strictly import-only event:
`{"mode":"STAGING_IMPORT_SMOKE"}`. The Signal handler tests core/AWS SDK
import and the staging bucket environment; Paper imports numpy, pandas,
yfinance, exchange_calendars, shared accounting and AWS SDK; Orchestrator
tests exchange-calendars, AWS SDK and child-function environment variables.
All respond with `STAGING_IMPORT_OK`, `broker_actions:false` and
`market_data_written:false`. No provider request, S3 object mutation,
ledger bootstrap, signal production, or broker action occurs on this path.

The new `infra/aws/smoke_independent_staging.sh` inspects the existing
Stack status, EventBridge rule `DISABLED`, S3 Versioning/Public Access Block,
all three Lambda runtime configurations, and invokes each staged Lambda with
the safe import-only event. It fails on Lambda `FunctionError` and displays a
bounded runtime error excerpt. The deployment script calls this smoke check
automatically **after** a successful separate-stack CloudFormation update.

From the existing checked-out branch, the single combined update+check is:

```bash
git pull --ff-only && bash infra/aws/deploy_independent_staging.sh
```

The command builds and deploys a **new source SHA-pinned artifact** to the
existing staging stack, then exercises the no-market smoke. It does not need
`STOCKLENS_RECREATE_ROLLED_BACK_STAGING=1` when the stack is already
`CREATE_COMPLETE`; that flag should not be passed again. The original
`stocklens-paper` stack remains unchanged. Successful import smoke **does
not authorize** enabling EventBridge or disconnecting the old GitHub source.

The first prospective market-data execution must target a genuinely completed
NYSE session after 18:00 New York local time. Never force an earlier session
when the vendor includes a partial bar for the current session. The staged
Paper book can begin only on the **next** real exchange session with a prior
signal generated **before that session's 09:30 ET open**. It is not permissible
to replay earlier sessions with newly generated timestamps and claim point-in-time
paper fills.


### AWS live-import smoke passed; next isolated provider + first-signal acceptance

On October 12, the account operator confirmed `UPDATE_COMPLETE` for the
isolated staging stack and **all three import-only Smoke checks passing**
(`SMOKE_PASS:signal`, `SMOKE_PASS:paper`, `SMOKE_PASS:orchestrator`).
S3 versioning/private-access checks passed and EventBridge remained `DISABLED`.
These facts prove runtime and packaging integrity, not market-data availability.

Next, use the **same shell in the existing checkout**, after updating the
branch that includes this acceptance harness:

```bash
git pull --ff-only && bash infra/aws/deploy_independent_staging.sh
```

Run the safe **read-only provider network probe**. It uses an actual Yahoo chart
HTTP GET from inside the candidate Signal Lambda, verifies that the expected QQQ
chart schema is reachable, and returns the count/latest calendar date; it
**does not write S3, declare today's session complete, produce a signal,
bootstrap a Paper portfolio, or contact a broker**:

```bash
bash infra/aws/accept_independent_staging.sh probe
```

Once the US regular market session for **2026-10-12** has completed and it is
**after 18:00 America/New_York on October 12** (01:00 Israel time on Oct 13),
run the first independent AWS signal **only**:

```bash
bash infra/aws/accept_independent_staging.sh signal 2026-10-12
```

The runner refuses an incomplete New York session, invokes Signal with
`STAGING_ONLY`, and independently downloads and checks three **versioned**
S3 receipts (actual adjusted QQQ CSV, source manifest, frozen Signal JSON).
It verifies all market/manifest/signal SHA links, 253-session fingerprint,
latest session, `SHADOW_ONLY_NO_BROKER_ACTIONS`, disabled broker permissions,
and first-write S3 version identities. A Lambda `FunctionError` is treated
as a failure even if the AWS CLI exits successfully.

The first signal is **not a Paper fill**; the independent Paper book can start
no earlier than the **next** completed XNYS trading session, with that prior
day's Signal already archived **before** the next market opening.

This verifies single-provider access and **internal** provenance only.
Identical adjusted-price/decision parity with the original yfinance generator,
second-vendor verification, intraday corporate-action evidence and full
prospective Paper continuity remain production cutover blockers. If Yahoo
limits/blocks AWS IP addresses, the read-only network probe will report a
runtime failure: do not fabricate data or silently replace the provider.


### Read-only frozen price-path parity (does not use a second provider)

The user verified the real AWS Yahoo networking probe returned 4,724 QQQ
chart bars (latest calendar date 2026-10-12) and all three Lambda imports
passed. The 2026-10-12 bar had not yet been certified complete.

The candidate Signal Lambda now supports an **additional safe mode**:
`STAGING_SAME_VENDOR_PATH_PARITY`. It reads Yahoo's QQQ adjusted daily
closes via (1) the direct Yahoo chart endpoint and (2) the original
frozen `stocklens.data.load_qqq_history` using pinned `yfinance`
with `auto_adjust=True`. It requires the exact same completed XNYS
session, ordered full calendars (no silent reindexing), near-identical
history prices, the same 253-session feature fingerprint, and the same
frozen current/previous decisions, weights, defense state and action.
It returns explicit diagnostics and **does not publish any signal**.

Before 18:00 America/New_York, the comparator only removes the current
day's incomplete bar **in-memory for this read-only diagnostic**, then
compares against the prior completed exchange session. This exception is
not available in the permanent signal archive writer.

To deploy the extended read-only probe into the existing staging stack
and run it directly from the same CloudShell checkout:

```bash
git pull --ff-only &&
bash infra/aws/deploy_independent_staging.sh &&
bash infra/aws/accept_independent_staging.sh parity
```

Expected success text: `SAME_YAHOO_TWO_PATH_PARITY_PASS`, along with
the last completed trading date, observed row count and whether today's
incomplete bar was excluded. Failure does **not** authorize an adjusted
threshold or deletion/overwrite of mismatched evidence; retain and debug
the numeric/date differences.

**Scope warning:** Yahoo direct chart versus yfinance is two processing/
retrieval paths for the **same ultimate Yahoo data source**, *not two
independent quote providers*. This pass cannot certify point-in-time
corporate actions, execution-quality bid/ask prices, market microstructure
or actual brokerage fills. The Paper session gates and disabled
EventBridge schedule remain unchanged.

# StockLens — complete-system closure and single-release acceptance ledger

**Scope:** frozen StockLens 8.0; AWS `stocklens-independent-staging` in `eu-central-1`; GitHub Draft PR #78.  
**As of:** 2026-10-13. **Purpose:** close everything deterministically in code and CI *before* ONE operator-reviewed AWS staging deploy. This document is not permission to trade, merge, bootstrap retrospectively, or modify `stocklens-paper`.

## Hard distinctions

- **CODE READY** means the change exists on the PR branch, with passing offline CI. It is NOT a deployed Lambda.
- **AWS VERIFIED** means CloudShell returned contemporaneous actual AWS runtime/S3 evidence.
- **EXTERNAL GATE** requires actual account/email/provider/broker or elapsed future market sessions. It cannot be fabricated by tests, GitHub or a date-stamped document.
- A target leverage of 3x is a **strategy state**, NOT proof of brokerage holdings or returns.
- Observed Yahoo QQQ/TQQQ one-minute prices plus modelled slippage/fees are **Paper accounting**, NOT exchange confirmations or broker fills.

## Last actually proven AWS evidence

- 2026-10-12: isolated staging deployed; Signal/Paper/Orchestrator/Watchdog import smoke passed 4/4. Signal completed-session: `STAGING_SIGNAL_AND_S3_RECEIPT_VERIFIED:2026-10-12`; QQQ market rows 4,724; Level 3, Defense false, Target leverage 3.0x, Action NO_CHANGE; no broker action.
- Combined Paper+Signal EventBridge remained **DISABLED**. 2026-10-13 operator CloudShell was blocked at `STAGING_SNS_EMAIL_UNCONFIRMED`; Signal-only automatic schedule NOT proven enabled.
- Later source changes added additional Lambda and watchers; **none of those source changes is AWS VERIFIED** until the final pinned staging deploy, smoke, and live evidence.
- Prior GitHub CI showed 793/793 tests passing on commit `df40b07`. New commits must establish their own independent green CI; never carry forward a previous green badge.

## Architecture being prepared (NO deployment yet)

```text
NYSE completed-session calendar + data guard
          |
          v
EventBridge Signal-only: 00:10 UTC Tue–Sat [OFF by default]
  -> Candidate Signal Lambda (pinned yfinance adjusted QQQ, frozen 8.0)
  -> private versioned S3: market/qqq/, manifests/qqq/, signals/
          |
          | 70-minute delay and immutable receipt prerequisite
          v
EventBridge Paper-only: 01:20 UTC Tue–Sat [OFF by default]
  -> Candidate Paper Lambda (never bootstraps on schedule)
  -> observed QQQ/TQQQ 1m execution prices; bounded catch-up
  -> S3: market/paper/, paper/sessions/, paper/continuity/,
         paper/book/.../genesis.json
          |
          v
Hourly independent Watchdog [ON]
  -> XNYS-aware late/missing signal detection from immutable activation marker
  -> Paper completeness/chain from durable Genesis (no manual CF start required)
  -> CloudWatch metrics/alarms -> encrypted Staging SNS topic -> CONFIRMED email

Manual-only: read-only Paper Preflight Lambda with no S3 PutObject permission.
Legacy combined Signal+Paper orchestrator: kept DISABLED.
Existing `stocklens-paper`: unchanged.
Broker/Excellence order authority: never enabled.
```

## Master acceptance register

| Track | Code action / invariant | Minimum acceptance evidence | State before final deploy |
|---|---|---|---|
| Frozen decision parity | No change to frozen StockLens 8.0; fingerprint/level/leverage/action guards | Exact artifact/commit + replay and verified S3 hash | CODE READY; original staging signal AWS VERIFIED |
| Market provenance | yfinance adjusted QQQ history, exchange calendar, immutable manifest/version/SHA | S3 server time, revision rejection, no partial daily bars | AWS VERIFIED for 2026-10-12 only |
| **Independent data-source parity** | Compare same-vendor paths and second economically independent source; isolate corporate actions/precision | Policy AND numerical feature-input evidence, no tolerance waiver | **EXTERNAL NO-GO** — direct Yahoo Chart drift remains (25 >8 binary32 ULP); independent vendor unproven |
| Signal automation | Single Signal-only scheduled Lambda, DST/holiday guard; no Paper calls | Actual EventBridge fire produces an immutable completed-session receipt on time | CODE READY; schedule NOT proven enabled |
| Paper first-session | Manual read-only preflight with separately scoped IAM (no `PutObject`), explicit prospective genesis commit | Observed 1m data, prior signal archived before open, five Lambda smoke passes, validated first Paper receipt and Genesis S3 version/SHA | CODE READY; first real prospective Paper receipt **NOT PROVEN** |
| Paper automation | Paper-only delayed schedule; no scheduled bootstrap, bounded catch-up, original ledger math, broker flags false | Existing verified Genesis and chain; a scheduled completed session with verified receipt | CODE READY; rule OFF by default |
| Delayed provider response | Current-day missing observed 1m bars must fail retryably *before* any MISSED write | Deliberate outage test + later actual recovery, without forged time | CODE READY; AWS test outstanding |
| Immutable Paper chain | Every forward receipt validated from durable Genesis; no skipping, counterfeit backfill or split books | Versioned S3 receipt SHA, exact signal/market pairing, independent ledger evaluation | Offline tests; forward AWS chain OUTSTANDING |
| Alerts | Watchdog checks missed signals, missing Paper, schedule-state drift, Lambda errors, heartbeat | SNS subscription Confirmed **and actual controlled alarm received in inbox** | **EXTERNAL NO-GO** — last confirmed status unconfirmed |
| Cost controls | Account-wide $20 AWS monthly Budget, 5 notifications; minimal invocation/log retention | Cloud billing actuals, alert receipt, account budget checked | Budget created; NOT a hard spending cap |
| Security | Minimal IAM scopes; read-only Preflight Lambda; no broker credentials, private S3 | Deployed IAM policies and Lambda handlers inspected, negative invocation tests | CODE READY; deployment runtime check outstanding |
| Schedules / redeploy | CF defaults all trading rules OFF; reject redeploy of active Signal/Paper/combined, or active signal-monitor marker | Post-deploy EventBridge rules correct, one delayed Paper timer only | CODE READY; runtime verification outstanding |
| Dashboard | Read-only, source-identified status/decisions/equity/chain and missing-evidence indicators | UI built from AWS immutable staging receipts, not only historical GitHub static JSON | **OPEN** — existing Amplify/GitHub portal is not independent staging cutover |
| Legacy producer exit | Run independent path in parallel; freeze old `stocklens-paper` read/write ledger | Multi-session independent AWS receipts, account inventory, reviewed cutover/rollback | **NO-GO** for production cutover |
| Broker readiness | Read-only reconciliation and broker-order authorization separate from Paper; kill-switch and limits | Real broker sandbox/reconciliation evidence; no order action in staging | **NOT STARTED / HUMAN-OWNED** — no real trading approval |

## Safe acceptance in ONE final staged release

1. **Pre-deploy**: pin exact Draft PR commit and green CI SHA. Confirm only the intended staging stack, owner AWS account, budget and CloudFormation change set. Back up references (stack, Lambda CodeSha256, S3 versions, existing Dynamo table). No destructive rollback or re-create; abort on active schedules or an existing activation marker.
2. **Deploy once**: build pinned Lambda ZIP; validate CloudFormation; deploy only `stocklens-independent-staging`; smoke import all **five** Lambdas. Confirm both Signal-only/Paper-only and old combined EventBridge rules are **DISABLED**; Watchdog hourly **ENABLED**; private S3 versioning, scoped IAM roles and alarms intact.
3. **Email acceptance**: subscribe/confirm Staging SNS recipient, send a controlled alarm, verify actual inbox delivery. An AWS Budget email is a *different* subscription.
4. **Signal activation**: run guarded `enable_staging_signal_only.sh check|activate` *once*, after alarm proof. S3 server-timestamped immutable activation marker precedes EventBridge enable. Verify first **actual scheduled** completed-session Signal (not a manual backfill) and Watchdog nonbreaching/missing data alerts.
5. **Paper prospective gate**: after a valid NEW completed session with prior close Signal genuinely archived before its open, call the dedicated **read-only** Paper Preflight. It cannot bootstrap and must reject orphaned candidate objects. Explicitly review historical data parity limitations and real TQQQ/QQQ observed minute bars.
6. **Manual first Paper genesis**: only an operator-approved, narrowly-scoped first Paper session via existing `STAGING_PAPER_ONLY bootstrap=true` after the preflight; then independent ledger/chain verification. NEVER do this retrospectively to claim prospective evidence. No broker.
7. **Paper automation gate**: verify fully committed and forward-qualified S3 Genesis/continuity, confirmed alerts and Signal schedule. Enable **only Paper-only** delayed EventBridge via guarded activation. Old combined orchestrator stays OFF. On current-day transient vendor data delay, alert/retry; never turn it into an irreversible missing session before proven absent.
8. **Prospective soak**: at least **20 completed XNYS sessions** with valid daily Signal; Paper chain with no unexpected gaps, DST/holiday and outage paths exercised. Compare actual costs and prove receipts survive GitHub publishing being unavailable. Record source mismatch diagnostics, not just matching policy state.
9. **Separate reviewed production read-side cutover only later**: change portal / old runtime consumers to immutable AWS evidence, retain Dynamo/S3 history and a rollback route. No broker orders as part of this release.

## Final gates that offline coding CANNOT close

- A live AWS CloudFormation deployment, IAM/resource inspection, controlled SNS inbox test and observing the next real scheduled market session.
- A reliable **second** historical/live market-data provider and its point-in-time adjustment semantics; Yahoo-to-Yahoo drift cannot be resolved by silently increasing tolerance.
- Independent broker/exchange evidence; read-only balance/order reconciliation and a separately authorized trading design if real capital is ever contemplated.
- Connected AWS staging read-side dashboard and migration strategy for the old Amplify/GitHub-published portfolio history.
- Sufficient prospective future market days, costs and market events. An offline test count or a retrospective signal timestamp is not proof of these.

## Safety invariants

**Never** auto-enable brokerage. **Never** assert broker fills from modeled prices. **Never** mark delayed/missing quotes as a successful signal. **Never** label a reconstructed/backdated Paper run as forward-qualified. **Never** merge Draft PR #78 or mutate `stocklens-paper` as a side effect of candidate deployment. **Never** call a green CI run an AWS end-to-end test. AWS Budget alerts do **not** cap billing.

## Final one-command staging release (prepared, NOT executed)

Once the **final** PR commit SHA has passing CI and the owner is ready for the
one reviewed CloudFormation update, cleanly check out that exact SHA in AWS
CloudShell and run:

```bash
export AWS_REGION=eu-central-1
export EXPECTED_STOCKLENS_RELEASE_COMMIT=<the exact green CI 40-character SHA>
bash infra/aws/release_staging_once.sh
```

This wrapper validates the pinned commit and transfer manifest, invokes the
existing fail-closed staging deployer, waits for **five** AWS Lambda import smoke
checks, then runs `infra/aws/audit_staging_release.sh`. The audit checks
actual deployed private/versioned S3, FIVE Lambda handlers, the IAM policy of
the read-only Preflight Lambda, encrypted SNS alarm wiring, three DISABLED
trading rules, hourly ENABLED watchdog, and the account budget <=$20.
It prints explicit NO-GOs; no activation, bootstrap, production change, or
broker capability is silently performed. If SNS is not confirmed, the audit
exits nonzero after a successful deploy and accurately reports a remaining
external gate.

After a true prospective first Paper receipt exists, the separate manual
`enable_staging_paper_only.sh check|activate YYYY-MM-DD` uses the existing
Budget/SNS/Signal preflight plus a read-only **full historical S3 chain audit**
inside the Paper Lambda. It NEVER bootstraps on schedule. Its opt-in is a
review of **Staging risk only**, not a waiver of numeric data-source parity
or authorization for real capital. Do not run it before the corresponding
actual complete NYSE session and real Genesis receipt exist.

Do not run these release actions merely to earn a green badge; the release
wrapper is *deliberately not called in CI*. IAM, billing, SNS delivery and
market data require real AWS/account evidence.

## One-time Paper bootstrap runbook (prepared, never auto-run)

The first genuine prospective Paper Genesis has a separately defended CLI:

```bash
bash infra/aws/bootstrap_staging_paper_once.sh YYYY-MM-DD
```

This command is valid **only** after the versioned prior-day Signal was
archived before the execution session opened, the current session closed,
both signals exist, and the read-only preflight passes before next NYSE open.
It checks budget/SNS/schedules, prompts for explicit first-book creation
consent, writes only the isolated Staging Paper account, verifies the new
Genesis and full continuity chain, and leaves Paper-only EventBridge
**DISABLED**. Any partial-write failure is a human S3 evidence recovery task,
not an automatic reset. The trading broker stays unconnected.

Do not substitute this command with an old retrospective backtest or a direct
Lambda bootstrap call; it would not establish prospective reliability.

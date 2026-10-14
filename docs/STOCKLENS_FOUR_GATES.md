# StockLens 8.0 — Four outstanding gates, code and production evidence

Release candidate: GitHub PR #78. This reference is intentionally NOT an AWS
deployment, not a production merge and not a real-money trading authorization.

## 1. AWS operational acceptance

Prepared already: pinned isolated Staging deployment, hourly watchdog,
Signal-only and Paper-only schedules OFF by default, independent read-only
Preflight and reviewed manual first Paper Genesis. The release's AWS IAM,
Lambda, S3, SNS, budget, alarm and EventBridge checks are under
`infra/aws/audit_staging_release.sh`. **Never enable all schedules as one
unobserved switch**: the first genuine Signal and Paper session, exact
S3 server timestamps, SNS test email and 20 forward XNYS session receipts must
be observed. AWS Budgets $20 alerts do not cap spending.

**Remaining external NO-GO**: actual authenticated AWS access to deploy, SNS
email subscription and receipt, and future market-session evidence.

## 2. Independent market-data validation

`infra/aws/second_vendor_parity.py` now accepts two independent
`Date,Close` CSV sources — existing frozen QQQ yfinance adjustment and an
independently obtained Alpaca historical stock-bars `adjustment=all`
export (split, dividend and spin-off adjusted). It checks dates, nonsynthetic
positive closes, the full frozen StockLens 8.0 replay decisions, mismatch
dates, adjustment declarations and both source SHA-256s. Diagnostics can
say `SECOND_VENDOR_POLICY_DIAGNOSTIC_MATCH`, **never** silently set
`second_provider_proven=true` or promote frozen production.

The earlier Yahoo Chart vs frozen-yfinance >8 float32 ULP mismatch remains
an actual unresolved **NO-GO**. Distinct vendor adjusted series are not
bitwise interchangeable; provider corporate-action revision timestamps,
point-in-time availability, licensed historical coverage and attribution
must be reconciled with real provider data. Do not loosen numeric tolerance.

For authorized local, offline source files:
```bash
python3 infra/aws/second_vendor_parity.py \
  --frozen local_frozen_qqq.csv \
  --independent local_alpaca_qqq_adjustment_all.csv \
  --session YYYY-MM-DD --licensed-asof YYYY-MM-DD
```
No provider credentials or account secrets should be placed in GitHub,
CloudWatch logs or this repository. Data access/entitlements are owner-owned.
This is NOT a vendor license purchase or an automatic market-data connection.

## 3. AWS Staging dashboard read side

A new **separately deployed**, JWT-authenticated `GET /v1/staging?dates=`
integration is defined in `infra/aws/staging-portal-readonly.yaml`. It
attaches to the *already Cognito-protected* portal HTTP API via parameters
`PortalApiId`, `PortalAuthorizerId` and the exact private Staging bucket.
The route requires JWT authorization and its Lambda is IAM-scoped to S3
GetObject/GetObjectVersion/ListBucket of signals, paper sessions and
continuity; no S3 PutObject, order submission, DynamoDB writes or broker
permission. `infra/aws/staging_portal_read.py` defines the pure S3
receipt summary and conservative invalid evidence statuses.

Existing `infra/aws/portal-readonly-api.yaml` now exposes the IDs needed
for that separate route; the base portal API **must already exist and be
correctly secured**. New login and read-only S3 controls in
`docs/portal.html` and `docs/portal-cloud.js` remain disabled unless
`docs/cloud-config.json` is set **by the owner** with
`enabled:true`, `staging_enabled:true` and genuine existing private
Cognito/OAuth settings. Do NOT publicly paste tokens, AWS keys or S3 URLs.

The portal verifies S3 object versions, SHA-256 bindings, basic frozen
signal and paper flags, and displays explicit missing / invalid statuses.
It does **not** independently prove the complete S3 Genesis-to-Paper chain,
vendor-independent pricing or actual broker fills.

**External NO-GO**: Portal API deployment, Cognito user creation, portal
access, successful private authenticated S3 fetch and phone/browser
interaction test. The existing Amplify static source/history remains distinct
from observed private Staging; no production read-side cutover yet.

## 4. Excellence broker-readiness / human financial gate

`broker_readonly_evidence.py` now permits strictly offline reconciliation
of two manually normalized CSV files, each with ONLY:
`Symbol,Quantity` columns. One file is the intended brokerage portfolio,
the other is a recent broker export. Both files must be actual account
snapshots; **never** substitute StockLens Paper holdings as broker fills.
The script rejects duplicates, invalid quantities, stale timestamps,
unexpected symbols and unknown file schemas, calculates exact Decimal
differences and returns file SHA-256 fingerprints.

```bash
python3 broker_readonly_evidence.py \
  --intended intended_positions.csv \
  --observed actual_positions_from_excellence.csv \
  --snapshot-at-utc 2026-10-14T05:00:00+00:00
```

Even a MATCH leaves `live_gate_eligible=false`, because CSV data do not
authenticate account ownership, open orders, cash/settlement, real-time
quotes, source API contract or order-entry controls. Brokerage connectivity,
permission and any eventual actual trading authorization are separate,
human-approved actions. Do not store identifying account numbers in the repo.

## End-state deployment order

Prepare exactly one reviewed Staging release commit with green CI. Deploy
Staging and verify its five Lambda import smokes and release audit, then
confirm private SNS inbox delivery. Deploy the **optional separate read-only
portal route** only when the Cognito-protected portal API and exact private
Staging bucket are known; its CF stack is deliberately not invoked by CI.
Activate Signal first, prove real scheduled events; prospectively bootstrap
Paper with explicit approval; prove first immutable receipt/Genesis; only
then consider separate Paper scheduling. Observe at least 20 actual sessions,
costs, outages and source drift before separately reviewing production
read-side migration. No real broker execution is included at any step.

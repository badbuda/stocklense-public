# AWS Paper Trading extension: update existing stocklens-paper stack

This is CODE STAGED FOR DEPLOYMENT, not yet a running AWS function.

The existing signal journal is preserved. A second Lambda runs at 09:20 UTC Tue-Sat and archives current completed NYSE-session forward modeled paper receipts in the SAME DynamoDB table with key YYYY-MM-DD#PAPER. It requires the current independent model accounting audit PASS, exactly one current session, observed QQQ/TQQQ 1-minute source, frozen prior signal available before market open, matched 09:31 sell / 09:32 buy receipts, and an already-published current shadow signal. The separate GitHub audit at 09:40 UTC verifies both immutable entries; GitHub read-only OIDC permissions and two repository variables remain unchanged.

Deployment: AWS CloudFormation, Frankfurt eu-central-1 -> stocklens-paper -> Update -> Replace current template -> upload infra/aws/paper-signal-journal.yaml from this branch's commit -> inspect change set and acknowledge IAM resources -> Update stack. Do not CREATE a new stack. CloudFormation should add PaperEvidenceLogs, PaperEvidenceRole, PaperEvidenceLambda, PaperEvidenceSchedule, PaperEvidencePermission, PaperEvidenceAlarm while preserving Signals. Verify UPDATE_COMPLETE and both scheduled Lambda functions.

This extension does not connect to a broker, stream live quotes, or prove exchange/broker fills. Its records are modeled paper executions calculated from vendor-observed minute-bar opens and assumed fees/slippage. No historical backfills, no automatic trading, no seller authorization. CloudWatch alarm has no SNS subscription yet. AWS Free Plan and DynamoDB retained table may incur charges.

## Timing race diagnosed from 2026-10-09 CloudWatch logs

At **03:10Z**, the signal Lambda rejected a stale 2026-10-07 signal; at **03:20Z**, paper-evidence Lambda fetched `docs/paper_portfolio_integrity.json` before it existed and received HTTP 404. GitHub did not publish 2026-10-08 signal/paper artifacts until **04:36Z**. The earlier 03:10/03:20 schedule cannot safely be considered a guaranteed dependency order for the separate GitHub pipeline.

**New contract (source change; requires CloudFormation UPDATE):** GitHub computes and publishes previous NY trading day, then AWS signal archive at **09:10Z Tue-Sat**, paper archive at **09:20Z Tue-Sat**, and GitHub AWS read-only audit at **09:40Z Tue-Sat**. For these post-midnight New York invocations the archive target is **previous NY calendar date**, never the current NY date. Refuse early hours, Sunday/Monday NY invocations, unmatched/stale signal dates, and missing actual previously published evidence. Holidays remain fail-closed and may cause expected missing-session alerts until an exchange-calendar-aware heartbeat is deployed. A green CI does not guarantee on-time GitHub publishing or AWS execution. Both DynamoDB writes remain conditional and idempotent for identical evidence only.

**Required rollout:** review a Change Set on the existing `stocklens-paper` CloudFormation stack (eu-central-1), upload this exact updated template, confirm **UPDATE_COMPLETE**, inspect deployed EventBridge schedules for **09:10Z/09:20Z** and CloudWatch log signatures for the NEXT genuinely completed market session. AWS permissions, live broker access and historical fills must not be changed. Confirm SNS email subscription and test a real alert separately. Do not claim that missed prior archival records were automatically recovered or that the generated paper fills were broker fills.

Historical note: the `2026-10-08` modeled paper session was subsequently published to GitHub, but its 03:10Z/03:20Z AWS archive calls failed. Updating the schedule alone does not replay the earlier failed invocations.

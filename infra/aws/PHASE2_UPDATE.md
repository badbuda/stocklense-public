# AWS Paper Trading extension: update existing stocklens-paper stack

This is CODE STAGED FOR DEPLOYMENT, not yet a running AWS function.

The existing signal journal is preserved. A second Lambda runs at 03:20 UTC Tue-Sat and archives current completed NYSE-session forward modeled paper receipts in the SAME DynamoDB table with key YYYY-MM-DD#PAPER. It requires the current independent model accounting audit PASS, exactly one current session, observed QQQ/TQQQ 1-minute source, frozen prior signal available before market open, matched 09:31 sell / 09:32 buy receipts, and an already-published current shadow signal. The separate GitHub audit at 03:40 UTC verifies both immutable entries; GitHub read-only OIDC permissions and two repository variables remain unchanged.

Deployment: AWS CloudFormation, Frankfurt eu-central-1 -> stocklens-paper -> Update -> Replace current template -> upload infra/aws/paper-signal-journal.yaml from this branch's commit -> inspect change set and acknowledge IAM resources -> Update stack. Do not CREATE a new stack. CloudFormation should add PaperEvidenceLogs, PaperEvidenceRole, PaperEvidenceLambda, PaperEvidenceSchedule, PaperEvidencePermission, PaperEvidenceAlarm while preserving Signals. Verify UPDATE_COMPLETE and both scheduled Lambda functions.

This extension does not connect to a broker, stream live quotes, or prove exchange/broker fills. Its records are modeled paper executions calculated from vendor-observed minute-bar opens and assumed fees/slippage. No historical backfills, no automatic trading, no seller authorization. CloudWatch alarm has no SNS subscription yet. AWS Free Plan and DynamoDB retained table may incur charges.

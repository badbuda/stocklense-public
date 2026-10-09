# AWS archive audit: NYSE holidays and operational limits

The GitHub read-only DynamoDB audit is scheduled 09:40 UTC Tue-Sat. It checks the preceding **America/New_York calendar date**, which is NOT always an exchange trading session. On Good Friday, Juneteenth, observed Independence Day, Christmas and other XNYS closures, a missing paper/signal archive is expected and should not be labeled data loss.

## Implementation

- `aws_journal_session_guard.py` uses the pinned `exchange-calendars==4.13.2` historical XNYS calendar to classify the previous NY date. It checks exceptional closures represented by that version and leaves early-close days as sessions requiring archival.
- `.github/workflows/aws-shadow-journal-audit.yml` checks session status **before** trying DynamoDB archive records. The AWS OIDC role and DynamoDB table **must still pass read-only preflight**, even if the exchange was closed.
- On closed XNYS dates, only the two session-specific `get-item` checks are skipped. The Issue #10 log identifies `NO_XNYS_SESSION_EXPECTED`, **not** `AWS_SIGNAL_AND_PAPER_AUDIT=PASS`.
- If calendar loading fails, the job fails; no fallback to a weekday approximation.
- Tests cover Good Friday, Juneteenth, July 4 observed, Christmas, weekends, ordinary sessions and the early-closing Friday after Thanksgiving.

## What this does NOT prove or fix

1. The **deployed EventBridge rules and AWS Lambda source** still use Tue-Sat cron and their existing previous-calendar-day assumptions. They can attempt to archive a holiday even if this GitHub *audit* correctly skips expecting records. This PR **does not fix the deployed AWS Lambda holiday scheduling**.
2. GitHub OIDC role currently has DynamoDB read permissions only. It cannot call `events:DescribeRule`, prove that each EventBridge rule is ENABLED, verify SNS subscription confirmation, send an actual email alert, or distinguish a missed invocation from a holiday. Those P0 dead-man checks remain OPEN.
3. A green GitHub audit proves only repository-to-AWS read-only table access and selected session-record consistency, never broker execution, full provenance, or 60 prospective sessions. No financial trading rights are added.
4. NYSE can declare unpredictable exceptional closures. Update the pinned calendar, verify authoritative announcements, and keep the archive evidence gates fail-closed; do not suppress a missing expected session solely because the source was unavailable.

**Remaining deployment acceptance:** AWS CloudFormation rule/Lambda holiday policy, read-only EventBridge rule state/observability, confirmed SNS and a received test email, plus a missed-invocation alert test. Require direct live stack verification; repository code and CI cannot prove deployment.

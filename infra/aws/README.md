# StockLens paper-only AWS bootstrap

This stack is a deliberately limited SHADOW SIGNAL ARCHIVE. It does not trade or count paper fills, and it does not grant ChatGPT AWS administration access.

1. Secure the AWS account root login with MFA. Confirm the plan and set budget alerts.
2. Open the CloudFormation console in eu-central-1 (Frankfurt): https://eu-central-1.console.aws.amazon.com/cloudformation/home?region=eu-central-1#/stacks
3. Choose Create stack, upload infra/aws/paper-signal-journal.yaml and set stack name stocklens-paper. Review the changes and acknowledge CAPABILITY_IAM.
4. Once CREATE_COMPLETE, open Outputs. Set GitHub repository Actions VARIABLES (not secrets) AWS_STOCKLENS_AUDIT_ROLE_ARN from GitHubAuditRoleArn and AWS_STOCKLENS_JOURNAL_TABLE from TableName.
5. Review and merge this branch before triggering the separate GitHub read-only audit workflow. The OIDC trust is restricted to the newly-created immutable GitHub owner and repository IDs on main only.
6. After GitHub publishes a completed US market day, the signal Lambda runs at 09:10 UTC Tue-Sat, archiving the previous New York calendar day. The paper Lambda follows at 09:20 UTC; the read-only audit runs at 09:40 UTC. Invalid or stale sessions fail closed, including NYSE weekday holidays. No synthetic quotes or retrospective paper fills are created.
7. Investigate errors via CloudWatch ErrorAlarm and Lambda logs. The alarm has no email configured yet. Do not assume a skipped or passing GitHub check proves execution.
8. A DynamoDB table is RETAINED if the stack is deleted; remove it explicitly when no longer needed. AWS service usage may cost money and Free Plan expires. Do not store AWS access keys in GitHub or send them to ChatGPT.

The trust subject is the public repo created on October 7 2026: badbuda owner ID 39247450, stocklense-public repository ID 1408609116. Verify the emitted OIDC subject before enabling the audit if repository ownership or OIDC configuration changed.

## Corrected after-publication schedule
AWS signal and modeled paper Lambdas are scheduled for **09:10Z** and **09:20Z**, Tuesday through Saturday UTC, to inspect the **previous New York calendar day** after the GitHub Shadow publisher. GitHub read-only AWS audit is **09:40Z**. Updating this repository **does not update deployed CloudFormation**: apply a reviewed UPDATE to existing `stocklens-paper` in `eu-central-1` using `paper-signal-journal.yaml` and verify `UPDATE_COMPLETE`, new EventBridge times, CloudWatch behavior and SNS. Fail closed when market holidays or delayed publisher prevent matching evidence; no synthetic backfill and no live orders.

## Independent missing-invocation watchdog (new, requires reviewed stack UPDATE)

The separate watchdog Lambda is scheduled **every six hours** at 00:15, 06:15, 12:15 and 18:15 UTC. It is independent of the two Tuesday-Saturday archive schedules. On every run it checks both EventBridge rules are ENABLED, target the correct Lambda ARNs and both archive Lambdas are Active. On Tue-Sat at 12:15 UTC it additionally checks that *each* archive Lambda has at least one CloudWatch invocation during 09:00-12:00 UTC, allowing >2 hours of metrics settling. The underlying archive schedules run Tue-Sat even on XNYS holidays, so this monitor tests **invocation**, not holiday archive expectations.

A dedicated `WatchdogErrorAlarm` sends failed inspections to the existing SNS topic. A separate `WatchdogHeartbeatAlarm` treats **two consecutive six-hour periods with zero or missing watchdog Invocations** as alarming: if the watchdog rule itself stops, CloudWatch can still notify the recipient. Six-hour monitoring may generate AWS charges; inspect the change set before deploy. The watchdog's IAM role has read-only EventBridge, Lambda and CloudWatch permissions and write access **only to its own logs**. It has no broker, trading or DynamoDB write permissions.

**NOT DEPLOYED BY GITHUB:** An AWS account owner must review the CloudFormation UPDATE and check existing Lambda/EventBridge/DynamoDB resources are not replaced. Wait for UPDATE_COMPLETE, check the two new alarms, observe a real scheduled watchdog invocation and received end-to-end alarm test, and perform a reversible disabled-rule test during an agreed maintenance window. Do not assume green CI proves AWS runtime. Monitor does not fix existing archive Lambda holiday failures or historic quote provenance. Disable neither archive rule just to make a test without an explicit maintenance plan.

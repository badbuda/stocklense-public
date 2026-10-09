# Deployed AWS runtime monitoring — read-only diagnostic, staged

This repository now contains `aws_runtime_watchdog.py`, an independent fail-closed **configuration inspector** for the existing `stocklens-paper` CloudFormation stack in `eu-central-1`. It never invokes Lambda, sends SNS messages, changes infrastructure, or places broker orders.

The script resolves deployed physical IDs from CloudFormation and checks both EventBridge rules are **ENABLED** with exact 09:10Z/09:20Z Tue-Sat schedules and expected Lambda targets; both Lambda functions are Active with successful last updates; both CloudWatch **Errors** alarms have actions enabled and point to the same SNS topic; and at least one email subscription has a confirmed ARN. A missing SNS topic (e.g. stack created with default `AlertEmail=''`) is a **failure**, not an implicit pass. It does not expose subscriber addresses in its report.

## Runbook

Do **not** claim this check ran on AWS just because local tests or GitHub CI are green. Current GitHub OIDC audit permissions only include DynamoDB read access. The read-only runtime inspector requires a separately reviewed IAM policy/deployment update before it can run under that role.

A minimal read-only permission review for the existing audit role must cover `cloudformation:DescribeStackResource` on the existing stack; `events:DescribeRule` and `events:ListTargetsByRule` on both existing rules; `lambda:GetFunctionConfiguration` on both existing Lambdas; `cloudwatch:DescribeAlarms`; and `sns:ListSubscriptionsByTopic` on the existing alert topic. Grant **no** EventBridge/Lambda/CloudWatch/SNS write actions and no broker credentials. Check the actual IAM policy against AWS authorization documentation before rollout.

After a reviewed IAM update and a **confirmed** email subscription, an operator with authorized read-only AWS credentials can run:

```bash
AWS_DEFAULT_REGION=eu-central-1 python aws_runtime_watchdog.py --stack stocklens-paper
```

Expected report status: `DEPLOYED_CONFIG_VERIFIED_NOT_DELIVERY_PROOF`. A missing resource, disabled rule, incorrect target, Lambda not Active, unwired alarm or unconfirmed email causes a nonzero exit. The script does **not** yet run automatically in the scheduled GitHub AWS audit; doing so before the IAM update would create a false failure. The monitoring deployment P0 remains **OPEN**.

## Independent acceptance still required

A confirmed SNS subscription is not proof an alarm notification reaches a human. Prove an actual received test alarm; demonstrate a disabled EventBridge rule is detected **by a running scheduled watchdog**, not merely by a mocked unit test; verify scheduled invocations with independent CloudWatch telemetry and account for exchange holidays, publisher delays and metrics ingestion lag. GitHub read-only DynamoDB archive success alone does not prove invocation health, monitoring delivery, source-price provenance or broker fills. A disabled GitHub workflow cannot monitor itself, so a separate external dead-man may ultimately be required.

The frozen 7.24 strategy and actual broker access are unchanged.

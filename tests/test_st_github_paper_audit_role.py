"""Source-only safety checks; no PyYAML, AWS SDK or network dependency."""
from pathlib import Path
import re

WORKFLOW=Path(".github/workflows/st-paper-daily-readonly.yml")
ROLE=Path("infra/aws/st-github-paper-audit-role.yaml")


def test_separate_github_oidc_role_trust_limited_to_main():
    source=ROLE.read_text()
    assert "GitHubSTPaperAcceptanceRole:" in source
    assert "AWS::IAM::Role" in source
    assert "sts:AssumeRoleWithWebIdentity" in source
    assert "'token.actions.githubusercontent.com:aud': 'sts.amazonaws.com'" in source
    assert ("'token.actions.githubusercontent.com:sub': "
            "'repo:badbuda@39247450/stocklense-public@1408609116:ref:refs/heads/main'") in source
    assert "stocklens-paper-GitHubAuditRole" not in source
    assert "RoleName:" not in source


def test_no_iam_or_s3_mutation_role_permissions():
    source=ROLE.read_text()
    for allowed in ("cloudformation:DescribeStacks", "events:DescribeRule",
                    "events:ListTargetsByRule", "lambda:GetFunctionConfiguration",
                    "lambda:InvokeFunction", "s3:GetObjectVersion",
                    "s3:GetBucketVersioning", "s3:ListBucketVersions",
                    "sns:ListSubscriptionsByTopic", "cloudwatch:DescribeAlarms"):
        assert allowed in source
    assert "OnlySTPaperReadinessInvoke" in source
    # Invoke is intentionally limited to a single ST Paper function, never PROD.
    assert re.search(
        r"Sid: OnlySTPaperReadinessInvoke[\s\S]*?"
        r"Action: lambda:InvokeFunction\s+Resource: !Sub "
        r"'arn:[^']*:function:stocklens-st-paper-candidate'",
        source
    )
    assert "IAM alone cannot constrain" in source
    for forbidden in ("Action: iam:", "Action: s3:Put", "Action: s3:Delete",
                      "Action: lambda:Update", "Action: events:Put",
                      "Action: cloudformation:Update", "Action: dynamodb:"):
        assert forbidden not in source
    assert "stocklens-prod" in source  # only readback to assert disarmed state
    assert "AWS_STOCKLENS_ST_AUDIT_ROLE_ARN" in source


def test_st_daily_acceptance_runs_only_after_paper_slot():
    source=WORKFLOW.read_text()
    assert "vars.AWS_STOCKLENS_ST_AUDIT_ROLE_ARN" in source
    assert "vars.AWS_STOCKLENS_AUDIT_ROLE_ARN" not in source
    assert "workflow_run:" not in source
    assert "cron: '15 14 * * 2-6'" in source
    assert "STAGING_PAPER_SCHEDULE_READINESS" not in source
    assert "python infra/aws/st_paper_closeout_readonly.py --session" in source


def test_st_v2_and_prod_legacy_schedules_stay_distinct():
    source=Path("infra/aws/st_paper_closeout_readonly.py").read_text()
    for expected in (
        'PROD_SIGNAL_CRON = "cron(30 2 ? * TUE-SAT *)"',
        'PROD_PAPER_CRON = "cron(20 3 ? * TUE-SAT *)"',
        'SIGNAL_CRON = "cron(30 5,8,11,12 ? * TUE-SAT *)"',
        'PAPER_CRON = "cron(0 13 ? * TUE-SAT *)"',
        '"ST_RECURRING_PAPER_SCHEDULE_DISABLED"',
        "ST_ALARM_OR_INSUFFICIENT_DATA",
        "PAPER_READINESS_NOT_QUALIFIED",
    ):
        assert expected in source
    for forbidden in ("put_object(", "put_rule(", "update_function_code(",
                      "delete_object(", "send_order(", "place_order("):
        assert forbidden not in source

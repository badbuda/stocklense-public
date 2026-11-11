"""Source-only controls for dedicated ST audit identity and post-Paper CI timing."""
from pathlib import Path
import yaml

WORKFLOW=Path(".github/workflows/st-paper-daily-readonly.yml")
ROLE=Path("infra/aws/st-github-paper-audit-role.yaml")

def cf_yaml():
    class Loader(yaml.SafeLoader):
        pass
    Loader.add_multi_constructor("!", lambda loader, tag, node: tag + ":" + str(node.value))
    return yaml.load(ROLE.read_text(),Loader=Loader)


def test_role_is_separate_from_legacy_dynamodb_only_audit_and_main_only():
    cloud=cf_yaml()
    assert list(cloud["Resources"]) == ["GitHubSTPaperAcceptanceRole"]
    r=cloud["Resources"]["GitHubSTPaperAcceptanceRole"]
    assert r["Type"] == "AWS::IAM::Role"
    trust=r["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]
    assert trust["Action"] == "sts:AssumeRoleWithWebIdentity"
    cond=trust["Condition"]["StringEquals"]
    assert cond["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    assert cond["token.actions.githubusercontent.com:sub"] == (
        "repo:badbuda@39247450/stocklense-public@1408609116:ref:refs/heads/main"
    )
    role_source=ROLE.read_text()
    assert "stocklens-paper-GitHubAuditRole" not in role_source
    assert "RoleName:" not in role_source


def test_no_iam_write_s3_write_or_production_lambda_invoke():
    doc=cf_yaml()
    statements=doc["Resources"]["GitHubSTPaperAcceptanceRole"]["Properties"]["Policies"][0]["PolicyDocument"]["Statement"]
    actions={action for stmt in statements
             for action in (stmt["Action"] if isinstance(stmt["Action"],list) else [stmt["Action"]])}
    assert "cloudformation:DescribeStacks" in actions
    assert "s3:GetObjectVersion" in actions
    assert "lambda:GetFunctionConfiguration" in actions
    assert "lambda:InvokeFunction" in actions
    assert not any(action.startswith(("iam:","dynamodb:","ec2:"))
                   for action in actions)
    assert not any("Put" in action or "Delete" in action or "Update" in action
                   for action in actions)
    for stmt in statements:
        if stmt["Action"] == "lambda:InvokeFunction":
            assert "function:stocklens-st-paper-candidate" in stmt["Resource"]
            assert "prod" not in stmt["Resource"]
    source=ROLE.read_text()
    assert "stocklens-prod" in source
    assert "AWS_STOCKLENS_ST_AUDIT_ROLE_ARN" in source
    assert "IAM alone cannot constrain" in source


def test_workflow_retries_only_after_actual_st_paper_schedule():
    import re
    source=WORKFLOW.read_text()
    assert "vars.AWS_STOCKLENS_ST_AUDIT_ROLE_ARN" in source
    assert "vars.AWS_STOCKLENS_AUDIT_ROLE_ARN" not in source
    assert "workflow_run:" not in source
    assert "cron: '15 14 * * 2-6'" in source
    assert "STAGING_PAPER_SCHEDULE_READINESS" not in source
    assert re.search(r"python infra/aws/st_paper_closeout_readonly[.]py --session",source)
    assert "stocklens-st-daily-readonly" in source


def test_acceptance_keeps_prod_disarmed_and_paper_real_not_fabricated():
    source=Path("infra/aws/st_paper_closeout_readonly.py").read_text()
    assert 'PROD_SIGNAL_CRON = "cron(30 2 ? * TUE-SAT *)"' in source
    assert 'PROD_PAPER_CRON = "cron(20 3 ? * TUE-SAT *)"' in source
    assert 'SIGNAL_CRON = "cron(30 5,8,11,12 ? * TUE-SAT *)"' in source
    assert 'PAPER_CRON = "cron(0 13 ? * TUE-SAT *)"' in source
    assert '"ST_RECURRING_PAPER_SCHEDULE_DISABLED"' in source
    assert "ST_ALARM_OR_INSUFFICIENT_DATA" in source
    assert "PAPER_READINESS_NOT_QUALIFIED" in source
    for forbidden in ("put_object(", "put_rule(", "update_function_code(",
                      "delete_object(", "send_order(", "place_order("):
        assert forbidden not in source

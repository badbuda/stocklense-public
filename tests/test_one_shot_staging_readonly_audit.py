"""Static safety contract for operator-triggered read-only staging audit."""
from pathlib import Path
import subprocess

SCRIPT = Path("infra/aws/one_shot_staging_readonly_audit.sh")


def test_shell_compiles_and_is_not_scheduled():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    text = SCRIPT.read_text()
    assert "read-only" in text.lower()
    assert "REF=810318f6d316199ef50c4bba3efb96a70646c28d" in text
    assert "2e550e4f032289b21f3a41bff7cb326eb6e0106a" in text
    assert "STAGING_SIGNAL_RECEIPT_AUDIT" in text
    assert "PAPER_GENESIS_PRESENT:ACCOUNTING_NOT_YET_VERIFIED" in text
    assert "NOT_PROVEN:EVENTBRIDGE_PROVENANCE,PROVIDER_PARITY,PAPER_ACCOUNTING,DASHBOARD_LIVE_SOURCE" in text


def test_no_aws_mutations_or_live_lambda_invocations():
    text = SCRIPT.read_text()
    for forbidden in (
        "aws events disable-rule", "aws events enable-rule",
        "aws cloudwatch disable-alarm-actions", "aws cloudwatch enable-alarm-actions",
        "aws lambda invoke", "aws lambda update-", "aws s3api put-object",
        "aws s3 cp", "aws dynamodb put-item", "aws dynamodb delete",
        "aws cloudformation execute-change-set", "aws cloudformation update-stack",
        "aws cloudformation delete", "aws sns publish",
        "aws sts assume-role", "aws iam ",
    ):
        assert forbidden not in text, forbidden
    assert "STAGING_RULE:" in text
    assert "LEGACY_RULE:" in text
    assert "LEGACY_ALARM:" in text
    assert "NO_LAMBDA_INVOKE:NO_S3_WRITE:NO_ORDER" in text

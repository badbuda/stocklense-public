"""Static safety regression for ST-only SNS onboarding and email alarm proof."""
from pathlib import Path
import re
import subprocess

SCRIPT = Path("infra/aws/stocklens_st_sns.sh")

def test_bash_syntax():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)

def test_st_scoping_and_account_guard():
    s = SCRIPT.read_text()
    assert "ACCOUNT=634740393398" in s
    assert "STACK=stocklens-st" in s
    assert "arn:aws:sns:eu-central-1:" in s
    assert "stocklens-st-candidate-alerts" in s
    assert '[[ "$(aws sts get-caller-identity' in s

def test_no_trading_or_paper_mutations():
    s = SCRIPT.read_text()
    for forbidden in [
        "aws events enable-rule", "aws events put-rule",
        "aws lambda invoke", "aws s3api put-object",
        "aws cloudformation update-stack", "aws cloudformation delete-stack",
        "aws cloudwatch delete-alarms", "aws cloudwatch put-metric-alarm",
    ]:
        assert forbidden not in s

def test_subscription_requires_email_confirmation():
    s = SCRIPT.read_text()
    assert "--protocol email" in s
    assert '[[ -n "$(confirmed)" ]]' in s
    assert '"PendingConfirmation"' in s
    assert "ST_SNS_UNCONFIRMED_CONFIRM_EMAIL_FIRST" in s

def test_alarm_test_is_confined_to_existing_stack_alarm():
    s = SCRIPT.read_text()
    assert "CandidateSignalErrorsAlarm" in s
    assert "aws cloudwatch describe-alarms --alarm-names" in s
    assert 'm.get("AlarmActions")!=[sys.argv[2]]' in s
    assert "ST_ALARM_ALREADY_ACTIVE_REFUSE_OVERRIDE" in s
    assert "aws cloudwatch set-alarm-state --alarm-name" in s
    assert "ST_EMAIL_DELIVERY_TEST_ONLY_NO_REAL_SIGNAL_ERROR" in s

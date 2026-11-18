"""Regression: AWS CloudShell scenario suite is strictly read only."""
from pathlib import Path
import re

P=Path(__file__).resolve().parents[1]/"infra/aws/st_cloudshell_all_scenarios.sh"

def test_console_suite_runs_actual_modules_and_aws_audit():
    src=P.read_text()
    required=(
        "tests/test_paper_eod_completeness.py",
        "tests/test_paper_transaction_recovery.py",
        "tests/test_paper_session_continuity.py",
        "tests/test_paper_portfolio_integrity.py",
        "tests/test_aws_schedule_watchdog.py",
        "tests/test_st_paper_operational_blockers_readonly.py",
        "st_paper_operational_blockers_readonly.py",
        "COMPLETED_XNYS_SESSION_CONFIRMED",
        "WRONG_AWS_ACCOUNT",
    )
    assert all(x in src for x in required)
    assert "LIVE_PAPER_RECOVERY_ATTESTED:FALSE" in src

def test_console_suite_no_aws_mutations_or_lambda_invocations():
    src=P.read_text()
    pattern=(r"aws\s+(?:lambda\s+invoke|s3\s+(?:cp|rm|sync|mv)|"
             r"events\s+(?:enable-rule|disable-rule)|"
             r"cloudwatch\s+set-alarm-state|"
             r"cloudformation\s+(?:deploy|update-stack))")
    assert not re.search(pattern,src)
    assert "aws sts get-caller-identity" in src

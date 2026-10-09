"""Static workflow contract: verify calendar gate cannot silently fail open."""
from pathlib import Path

W=Path(".github/workflows/aws-shadow-journal-audit.yml").read_text()


def test_previous_xnys_session_gate_applies_to_both_journal_reads():
    assert W.count("steps.market_calendar.outputs.required == 'true'") == 2
    assert "python aws_journal_session_guard.py --github-output" in W
    assert "exchange-calendars==4.13.2" in W
    assert "id: market_calendar" in W


def test_authentication_preflight_still_runs_when_xnys_closed():
    before=W.split("- name: Classify previous NY local day",1)[0]
    after=W.split("- name: Classify previous NY local day",1)[1]
    assert 'Missing AWS_STOCKLENS_AUDIT_ROLE_ARN' in before
    assert "- name: Assume temporary read-only AWS role" in after
    block=after.split("- name: Verify the scheduled completed-session signal",1)[0]
    assert "aws sts get-caller-identity" in block
    assert "aws dynamodb describe-table" in block


def test_qualified_skip_reporting_is_not_false_success():
    assert "MARKET_CALENDAR_OUTCOME" in W
    assert "NO_XNYS_SESSION_EXPECTED;IDENTITY_AND_TABLE_PREFLIGHT=" in W
    assert 'if [[ "${MARKET_CALENDAR_OUTCOME}" == "success"' in W
    assert "AWS_SIGNAL_AND_PAPER_AUDIT" in W
    assert "gh issue comment 10" in W

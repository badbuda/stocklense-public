from pathlib import Path
import ast
T=Path("infra/aws/paper-signal-journal.yaml").read_text()
SRC=Path("infra/aws/paper-evidence-handler.py").read_text()
W=Path(".github/workflows/aws-shadow-journal-audit.yml").read_text()

def test_inline_code_matches_python_and_compiles():
    assert T.count("ZipFile: |")==2
    extracted=T.split("ZipFile: |\n")[-1].split("\n  PaperEvidenceSchedule:")[0]
    inline="\n".join(s[10:] if s.startswith("          ") else s for s in extracted.splitlines()).strip()+"\n"
    assert inline==SRC.strip()+"\n"
    ast.parse(inline)

def test_real_qqq_tqqq_only_no_broker_orders():
    assert "YFINANCE_1M_RAW" in SRC and "SHADOW_ONLY_NO_BROKER_ACTIONS" in SRC
    assert '"broker_fills_observed":{"BOOL":False}' in SRC
    assert '"broker_orders_authorized":{"BOOL":False}' in SRC
    assert 'day+"#PAPER"' in SRC
    assert "attribute_not_exists(session_date)" in SRC
    assert "ReturnValuesOnConditionCheckFailure" in SRC
    assert "DIVERGENT_PAPER_DUPLICATE" in SRC

def test_two_isolated_scheduled_lambdas_and_no_secrets():
    assert T.count("Type: AWS::Lambda::Function")==2
    assert "cron(20 3 ? * TUE-SAT *)" in T
    assert "AWS_PROSPECTIVE_PAPER=PASS_MODELED_ONLY" in W
    assert "AWS_STOCKLENS_AUDIT_ROLE_ARN" in W
    assert "AWS_ACCESS_KEY_ID" not in W


def test_cloudformation_inline_python_is_small_and_portable():
    assert len(SRC) < 4096


def test_aws_email_alarm_and_duplicate_guards():
    assert 'EmailAlertsConfigured' in T
    assert 'AWS::SNS::Subscription' in T
    assert T.count('ReturnValuesOnConditionCheckFailure')==2
    assert T.count('DIVERGENT_')>=2
    assert T.count('RetentionInDays: 30')==2

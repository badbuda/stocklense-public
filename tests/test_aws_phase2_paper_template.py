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
    assert T.count("Type: AWS::Lambda::Function")==3
    assert "cron(20 9 ? * TUE-SAT *)" in T
    assert "cron(10 9 ? * TUE-SAT *)" in T
    assert "40 9 * * 2-6" in W
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
    assert T.count('RetentionInDays: 30')==3


def _audit_paper_python():
    """Execute the exact Python script embedded in the GitHub AWS audit step."""
    import textwrap
    section=W.split("- name: Validate separate modeled paper record in AWS; never broker fills",1)[1]
    script=section.split("python3 - <<'PY'\n",1)[1].split("\n          PY",1)[0]
    return textwrap.dedent(script)


def _run_audit_paper(monkeypatch, *, wrong_key=False, tampered=False, session="2026-10-08"):
    import contextlib
    import hashlib
    import io
    import json
    monkeypatch.setenv("SESSION",session)
    row={"session_date":"2026-10-08",
         "execution_source":"YFINANCE_1M_RAW",
         "trade_count_session":1}
    trades=[{"execution_session":"2026-10-08","symbol":"TQQQ","side":"BUY"}]
    # Match the archived Lambda's exact payload schema, including its trs key.
    payload={"row":row,("trades" if wrong_key else "trs"):trades}
    body=json.dumps(payload,sort_keys=True,separators=(",",":"))
    entry={"broker_orders_authorized":{"BOOL":False},
           "broker_fills_observed":{"BOOL":False},
           "paper_evidence_json":{"S":body},
           "paper_sha256":{"S":hashlib.sha256(body.encode()).hexdigest()}}
    if tampered:
        entry["paper_sha256"]["S"]="0"*64
    namespace={"open":lambda name,*args,**kw:io.StringIO(json.dumps({"Item":entry}))}
    out=io.StringIO()
    with contextlib.redirect_stdout(out):
        exec(compile(_audit_paper_python(),"github-aws-paper-audit","exec"),namespace)
    return out.getvalue()


def test_github_audit_reads_exact_lambda_paper_schema(monkeypatch):
    assert '"trs":mt' in SRC
    assert 'paper.get("trs")' in W
    assert 'paper["trades"]' not in W
    assert "AWS_PROSPECTIVE_PAPER=PASS_MODELED_ONLY;session=2026-10-08" in _run_audit_paper(monkeypatch)


def test_github_audit_rejects_original_trades_key_bug(monkeypatch):
    import pytest
    with pytest.raises(SystemExit,match="AWS_PAPER_TRADE_COUNT_MISMATCH"):
        _run_audit_paper(monkeypatch,wrong_key=True)


def test_github_audit_rejects_tampered_archive(monkeypatch):
    import pytest
    with pytest.raises(SystemExit,match="AWS_PAPER_EVIDENCE_TAMPERED"):
        _run_audit_paper(monkeypatch,tampered=True)


def test_github_audit_rejects_another_session(monkeypatch):
    import pytest
    with pytest.raises(SystemExit,match="AWS_PAPER_DATE_OR_SOURCE_MISMATCH"):
        _run_audit_paper(monkeypatch,session="2026-10-07")


def test_aws_audit_result_is_visible_and_rechecks_on_workflow_change():
    assert "issues: write" in W
    assert "AWS_SIGNAL_AND_PAPER_AUDIT" in W
    assert "github.event_name == 'push'" in W
    assert "always()" in W
    assert "gh issue comment 10" in W

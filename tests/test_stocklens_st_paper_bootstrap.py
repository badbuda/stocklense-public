"""Regression tests for isolated prospective modeled Paper initialization."""
from pathlib import Path
import subprocess
import pytest
from infra.aws import stocklens_st_paper_bootstrap as mod

def test_compiles():
    subprocess.run(["python","-m","py_compile","infra/aws/stocklens_st_paper_bootstrap.py"],check=True)

def test_activation_remains_disabled():
    txt=Path("infra/aws/stocklens_st_paper_bootstrap.py").read_text()
    assert 'STACK = "stocklens-st"' in txt
    assert 'PROD = "stocklens-prod"' in txt
    assert 'choices=("check","bootstrap")' in txt
    assert '"STAGING_PAPER_BOOTSTRAP_PREFLIGHT"' in txt
    assert '"STAGING_PAPER_SCHEDULE_READINESS"' in txt
    assert "CandidatePaperPreflightRole" in txt
    assert 'check_rule(prod,"CandidateSignalOnlyRuleName","DISABLED")' in txt
    assert "ST_PAPER_SCHEDULE_REMAINS_DISABLED" in txt

def test_require_read_only_preflight_response():
    data={"status":"STAGING_PAPER_BOOTSTRAP_PREFLIGHT_PASS_READ_ONLY",
          "session":"2026-10-30","prior_session":"2026-10-29",
          "market_source":"YFINANCE_1M_RAW","paper_accounting_audit":mod.AUDIT,
          "paper_model_equity":100000,"paper_model_trades":1,
          "model_candidate_sha256":"a"*64,
          "current_signal_s3_version_id":"v1","prior_signal_s3_version_id":"v0",
          "current_signal_s3_sha256":"a"*64,"prior_signal_s3_sha256":"b"*64}
    for key in ("broker_actions","broker_orders","broker_fills","market_data_written","paper_data_written","genesis_written","prospective_bootstrap_authorized"):
        data[key]=False
    mod.validate_preflight(data,"2026-10-30")
    data["broker_orders"]=True
    with pytest.raises(RuntimeError,match="PREFLIGHT_UNSAFE_FLAG"):
        mod.validate_preflight(data,"2026-10-30")


def test_status_presence_is_read_only_and_distinguishes_missing_second_signal(monkeypatch,capsys):
    monkeypatch.setattr(mod,"preconditions",lambda:("paper-preflight","paper"))
    keys=[]
    def head(bucket,key):
        keys.append(key)
        assert bucket==mod.BUCKET
        if key=="signals/2026-10-29.json":
            return {"VersionId":"prior","LastModified":"2026-10-30T02:30:00Z"}
        return None
    monkeypatch.setattr(mod,"safe_head",head)
    monkeypatch.setattr(mod,"invoke",lambda *args,**kwargs: pytest.fail("no Lambda invocation in status"))
    mod.status("2026-10-30")
    output=capsys.readouterr().out
    assert "PRIOR_SIGNAL=PRESENT:CURRENT_SIGNAL=MISSING:GENESIS=ABSENT" in output
    assert "WAITING_FOR_TWO_VERSIONED_SIGNALS:NO_WRITES" in output
    assert keys==[
        "signals/2026-10-29.json",
        "signals/2026-10-30.json",
        "paper/book/NEW_AWS_INDEPENDENT_STAGING_BOOK/genesis.json",
    ]


def test_status_all_present_does_not_pretend_preflight_pass(monkeypatch,capsys):
    monkeypatch.setattr(mod,"preconditions",lambda:("preflight","paper"))
    monkeypatch.setattr(mod,"safe_head",lambda *a:{"VersionId":"v1","LastModified":"X"}
                        if not a[1].endswith("/genesis.json") else None)
    mod.status("2026-10-30")
    output=capsys.readouterr().out
    assert "RUN_check_FOR_FULL_READ_ONLY_ACCOUNTING_PREFLIGHT" in output
    assert "READ_ONLY_FIRST_ST_PAPER_CHECK_PASS" not in output


def test_status_existing_genesis_never_bootstraps(monkeypatch,capsys):
    monkeypatch.setattr(mod,"preconditions",lambda:("preflight","paper"))
    monkeypatch.setattr(mod,"safe_head",lambda *a:{"VersionId":"v1","LastModified":"X"})
    mod.status("2026-10-30")
    assert "BOOK_ALREADY_EXISTS:NO_BOOTSTRAP" in capsys.readouterr().out


def test_safe_s3_head_404_is_missing_but_403_fails_closed(monkeypatch):
    class Completed:
        def __init__(self,code,stdout="",stderr=""):
            self.returncode=code;self.stdout=stdout;self.stderr=stderr
    monkeypatch.setattr(mod.subprocess,"run",
        lambda *a,**kw:Completed(1,stderr="An error occurred (404) when calling HeadObject"))
    assert mod.safe_head(mod.BUCKET,"signals/2026-10-30.json") is None
    monkeypatch.setattr(mod.subprocess,"run",
        lambda *a,**kw:Completed(1,stderr="An error occurred (403) AccessDenied"))
    with pytest.raises(RuntimeError,match="ST_S3_HEAD_FAILED"):
        mod.safe_head(mod.BUCKET,"signals/2026-10-30.json")
    monkeypatch.setattr(mod.subprocess,"run",
        lambda *a,**kw:Completed(0,stdout='{"VersionId":"null","LastModified":"X"}'))
    with pytest.raises(RuntimeError,match="ST_UNVERSIONED_OR_UNTIMED"):
        mod.safe_head(mod.BUCKET,"signals/2026-10-30.json")


def test_bootstrap_requires_short_explicit_yes_before_aws(monkeypatch):
    monkeypatch.setattr(mod.sys,"argv",["bootstrap.py","bootstrap"])
    monkeypatch.setattr(mod,"preconditions",lambda:pytest.fail("approval check must be before AWS"))
    with pytest.raises(RuntimeError,match="BOOTSTRAP_--yes_REQUIRED"):
        mod.main()


def test_read_only_check_rejects_yes_before_aws(monkeypatch):
    monkeypatch.setattr(mod.sys,"argv",["bootstrap.py","check","--yes"])
    monkeypatch.setattr(mod,"preconditions",lambda:pytest.fail("no AWS on disallowed flag"))
    with pytest.raises(RuntimeError,match="READ_ONLY_MODE_MUST_NOT_APPROVE"):
        mod.main()


def test_bootstrap_yes_keeps_preflight_and_only_one_paper_write(monkeypatch):
    events=[]
    monkeypatch.setattr(mod.sys,"argv",["bootstrap.py","bootstrap","--yes"])
    def pre():
        events.append("read_only_aws_guards")
        return "preflight","paper"
    def invoke(name,payload):
        assert name=="preflight"
        assert payload=={"mode":"STAGING_PAPER_BOOTSTRAP_PREFLIGHT",
                         "expected_session":"2026-10-30","bootstrap":False}
        events.append("preflight_invoke")
        return {"status":"stub"}
    monkeypatch.setattr(mod,"preconditions",pre)
    monkeypatch.setattr(mod,"invoke",invoke)
    monkeypatch.setattr(mod,"validate_preflight",lambda *args:events.append("validate"))
    monkeypatch.setattr(mod,"bootstrap",lambda *args:events.append("bootstrap"))
    mod.main()
    assert events==["read_only_aws_guards","preflight_invoke","validate","bootstrap"]

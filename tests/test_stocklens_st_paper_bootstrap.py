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

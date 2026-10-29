"""Safe ST import/network probe forbids signal writes, Paper and broker modes."""
from pathlib import Path
import subprocess
import pytest
from infra.aws import stocklens_st_runtime_probe as p

def test_probe_compiles():
    subprocess.run(["python","-m","py_compile","infra/aws/stocklens_st_runtime_probe.py"],check=True)

def test_exact_two_read_only_lambda_modes():
    text=Path("infra/aws/stocklens_st_runtime_probe.py").read_text()
    assert 'probe("STAGING_IMPORT_SMOKE","STAGING_IMPORT_OK")' in text
    assert 'probe("STAGING_VENDOR_NETWORK_PROBE","STAGING_VENDOR_NETWORK_OK")' in text
    for forbidden in ("STAGING_ONLY", "STAGING_SIGNAL_SCHEDULED",
                      "STAGING_PAPER_ONLY", "STAGING_PAPER_CATCHUP",
                      '"bootstrap":true', "aws events enable-rule",
                      "aws s3api put-object"):
        assert forbidden not in text

def test_wrong_account_blocks_before_invocation(monkeypatch):
    monkeypatch.setattr(p,"aws",lambda a,b,*args:{"Account":"WRONG_ACCOUNT"})
    with pytest.raises(RuntimeError,match="WRONG_AWS_ACCOUNT"):
        p.preconditions()

def test_runtime_probe_rejects_function_errors(monkeypatch,tmp_path):
    def fake(service,op,*args):
        if service=="lambda" and op=="invoke":
            Path(args[-1]).write_text('{"status":"bad"}')
            return {"StatusCode":200,"FunctionError":"Unhandled"}
        raise RuntimeError("UNEXPECTED_CALL")
    monkeypatch.setattr(p,"aws",fake)
    with pytest.raises(RuntimeError,match="UNVERIFIED"):
        p.probe("STAGING_IMPORT_SMOKE","STAGING_IMPORT_OK")


def test_same_vendor_parity_never_proves_second_provider(monkeypatch):
    import json
    from pathlib import Path
    def fake(service,op,*args):
        assert (service,op)==("lambda","invoke")
        Path(args[-1]).write_text(json.dumps({
            "status":"STAGING_SAME_VENDOR_PATH_PARITY_PASS",
            "provider":"YAHOO_CHART_VS_YFINANCE_YAHOO_AUTO_ADJUST",
            "broker_actions":False,"market_data_written":False,
            "second_provider_proven":False,
            "calendar_equal":True,"numeric_rounding_compatible":True,
            "feature_fingerprints_equal":True,"decisions_equal":True,
            "latest_action_equal":True
        }))
        return {"StatusCode":200}
    monkeypatch.setattr(p,"aws",fake)
    p.same_vendor_parity()


def test_same_vendor_parity_mismatch_is_blocker(monkeypatch):
    import json
    from pathlib import Path
    def fake(service,op,*args):
        Path(args[-1]).write_text(json.dumps({
            "status":"STAGING_SAME_VENDOR_PATH_PARITY_MISMATCH",
            "provider":"YAHOO_CHART_VS_YFINANCE_YAHOO_AUTO_ADJUST",
            "broker_actions":False,"market_data_written":False,
            "second_provider_proven":False,
            "calendar_equal":True,"numeric_rounding_compatible":False,
            "feature_fingerprints_equal":True,"decisions_equal":True,
            "latest_action_equal":True
        }))
        return {"StatusCode":200}
    monkeypatch.setattr(p,"aws",fake)
    with pytest.raises(RuntimeError,match="ST_SAME_VENDOR_PARITY_BLOCKED"):
        p.same_vendor_parity()

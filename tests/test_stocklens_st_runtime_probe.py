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

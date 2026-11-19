#!/usr/bin/env python3
"""ST Paper: verify *deployed* Lambda ZIP vs tested public economic modules.

CloudShell ONLY. AWS API read operations: sts:GetCallerIdentity and
lambda:GetFunction. AWS Lambda itself is NEVER invoked. Never PUT S3, change
alarms/EventBridge, touch PROD, place broker orders or upload private code.
Lambda source ZIP is downloaded to a temporary LOCAL directory (not GitHub).
Optional forced scenario suite imports economic modules out of the exact
deployed ZIP; persisted audit tests use public ledger/persistence adapters.
This is NOT direct testing of the private independent_paper.handler wiring.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
import zipfile

ACCOUNT = "634740393398"
REGION = "eu-central-1"
NAME = "stocklens-st-paper-candidate"
ST_BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
HANDLER = "infra.aws.independent_paper.handler"
PINNED_LAMBDA_SHA_B64 = "YKpLN8Ks36blX4J9z+GnDKx9fCN87tA7wwc5Sc/25WQ="
MAX_ZIP_BYTES = 100_000_000

# Current tested main files. Git blob SHA is derived from RAW bytes, not
# a Python source comparison or a version string.
PINNED_PUBLIC_MODULE_BLOBS = {
    "stocklens/__init__.py": "09cdf5a6f2f96f89eecf3c338170bf034e9c430a",
    "stocklens/core.py": "258c6918ea10456754bcd26f782af77545a56b2b",
    "stocklens/paper.py": "ea8427b32899f713468f072dee80ee71216289bf",
    "paper_rebalance_math.py": "be0b104495282c070fe0fbef62153347c2d36f9a",
}
TESTS = (
    "tests/test_paper_order_lifecycle_matrix.py",
    "tests/test_signal_to_paper_order_handoff.py",
    "tests/test_paper_execution_contract.py",
    "tests/test_paper_transaction_recovery.py",
    "tests/test_paper_eod_completeness.py",
    "tests/test_paper_session_continuity.py",
    "tests/test_paper_tax_receipts.py",
    "tests/test_paper_portfolio_integrity.py",
)


def require(condition, label):
    if not condition:
        raise RuntimeError(label)


def git_blob_sha(raw: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def assert_local_pins(repo: Path):
    for name, expected in PINNED_PUBLIC_MODULE_BLOBS.items():
        path = repo / name
        require(path.is_file() and git_blob_sha(path.read_bytes()) == expected,
                "LOCAL_TESTED_CODE_NOT_PINNED:" + name)
    for path in TESTS:
        require((repo / path).is_file(), "LOCAL_TEST_SUITE_MISSING:" + path)


def validate_config(cfg: dict):
    require(cfg.get("FunctionName") == NAME, "NOT_ST_PAPER_FUNCTION")
    require(cfg.get("State") == "Active" and
            cfg.get("LastUpdateStatus") == "Successful",
            "ST_PAPER_LAMBDA_NOT_ACTIVE")
    require(cfg.get("Handler") == HANDLER, "UNEXPECTED_PAPER_HANDLER")
    require(cfg.get("Environment", {}).get("Variables", {}).get(
        "STOCKLENS_DATA_BUCKET") == ST_BUCKET, "PAPER_WRONG_BUCKET_STOP")
    require(cfg.get("CodeSha256") == PINNED_LAMBDA_SHA_B64,
            "PAPER_DEPLOYMENT_CHANGED_SINCE_LAST_AWS_AUDIT_STOP")


def authenticated_download(sts, lam):
    require(sts.get_caller_identity().get("Account") == ACCOUNT,
            "WRONG_AWS_ACCOUNT_STOP")
    response = lam.get_function(FunctionName=NAME)
    cfg = response.get("Configuration", {})
    validate_config(cfg)
    code = response.get("Code", {})
    require(code.get("RepositoryType") == "S3" and
            isinstance(code.get("Location"), str), "NOT_VERSIONED_LAMBDA_ZIP")
    u = urllib.parse.urlparse(code["Location"])
    require(u.scheme == "https" and
            bool(u.hostname) and
            (u.hostname.endswith(".amazonaws.com") or
             u.hostname.endswith(".amazonaws.com.cn")),
            "UNEXPECTED_LAMBDA_CODE_DOWNLOAD_DOMAIN")
    with urllib.request.urlopen(code["Location"], timeout=35) as r:
        raw = r.read(MAX_ZIP_BYTES + 1)
    require(len(raw) <= MAX_ZIP_BYTES and len(raw) > 0,
            "LAMBDA_ZIP_TOO_LARGE_OR_EMPTY")
    observed = base64.b64encode(hashlib.sha256(raw).digest()).decode()
    require(observed == cfg["CodeSha256"], "DOWNLOADED_ZIP_SHA256_MISMATCH")
    return raw, cfg


def inspect_zip(raw: bytes, repo: Path):
    """Only read; do not execute any untrusted ZIP module here."""
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        require(len(names) == len(set(names)), "DUPLICATE_ZIP_ENTRIES")
        require(len(names) < 100000 and all(
            not name.startswith("/") and
            "\\" not in name and ".." not in Path(name).parts
            for name in names), "UNSAFE_ZIP_FILE_NAMES")
        z.testzip()  # CRC check all files before any execution
        report = {}
        for name, expected in PINNED_PUBLIC_MODULE_BLOBS.items():
            present = name in names
            actual = git_blob_sha(z.read(name)) if present else None
            report[name] = {
                "bundled": present,
                "deployed_git_blob_sha1": actual,
                "public_tested_git_blob_sha1": expected,
                "matches_tested_code": present and actual == expected,
            }
        independent_handler = "infra/aws/independent_paper.py"
        return report, {
            "module_bundled": independent_handler in names,
            "module_sha256": (hashlib.sha256(z.read(independent_handler)).hexdigest()
                              if independent_handler in names else None),
            "handler_executed": False,
            "private_source_disclosed": False,
        }


def execute_deployed_economic_module_scenarios(raw: bytes, repo: Path):
    """Execute tests on the ZIP's actual economic Python modules, in temporary work.

    Fail closed if any tested economic module does not exist in the ZIP.
    This does not run the private handler or mock S3 adapter inside the ZIP.
    """
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        for name in PINNED_PUBLIC_MODULE_BLOBS:
            require(name in z.namelist(), "DEPLOYED_MODULE_UNAVAILABLE:" + name)
        with tempfile.TemporaryDirectory(prefix="stocklens-lambda-zip-offline-") as work:
            root = Path(work)
            for name in PINNED_PUBLIC_MODULE_BLOBS:
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(name))
            # No shell, no dynamic untrusted handler import, no external network.
            # The exact economic module from the ZIP loads BEFORE pytest.
            launcher = StringRunnerScript
            env = dict(os.environ)
            env["STOCKLENS_TEST_DEPLOYED_RUNTIME_ROOT"] = str(root)
            env["STOCKLENS_TEST_REPO_ROOT"] = str(repo)
            env["AWS_EC2_METADATA_DISABLED"] = "true"
            env.pop("AWS_ACCESS_KEY_ID", None)
            env.pop("AWS_SECRET_ACCESS_KEY", None)
            env.pop("AWS_SESSION_TOKEN", None)
            proc = subprocess.run([sys.executable, "-c", launcher],
                                  cwd=root, env=env, timeout=180,
                                  check=False)
            return proc.returncode


StringRunnerScript = r'''
from pathlib import Path
import os, sys, socket
runtime = Path(os.environ["STOCKLENS_TEST_DEPLOYED_RUNTIME_ROOT"]).resolve()
repo = Path(os.environ["STOCKLENS_TEST_REPO_ROOT"]).resolve()
sys.path.insert(0, str(runtime))
sys.path.insert(1, str(repo))
# Any test accidentally touching AWS network must fail loudly.
def blocked(*args, **kwargs):
    raise RuntimeError("NETWORK_FORBIDDEN_IN_OFFLINE_DEPLOYED_MODULE_TEST")
socket.create_connection = blocked
socket.socket.connect = blocked
try:
    import boto3
    boto3.client = blocked
    boto3.resource = blocked
except ImportError:
    pass
# The deployed ZIP intentionally includes only a subset of stocklens.
# Preserve the deployed __init__/core/paper modules while finding unrelated,
# test-only helpers (notably stocklens.tax_research) in the verified checkout.
# Do NOT prepend repository stocklens/ to __path__, which could silently
# replace the deployed economic modules under test.
import stocklens
assert Path(stocklens.__file__).resolve() == (
    runtime / "stocklens/__init__.py"
).resolve(), "NOT_USING_DEPLOYED_STOCKLENS_PACKAGE"
stocklens.__path__.append(str(repo / "stocklens"))
from stocklens import paper, core, tax_research
import paper_rebalance_math
assert Path(tax_research.__file__).resolve() == (
    repo / "stocklens/tax_research.py"
).resolve(), "TEST_ONLY_TAX_HELPER_NOT_FROM_PUBLIC_CHECKOUT"
def assert_economic_import_provenance():
    for mod, path in ((paper, "stocklens/paper.py"),
                      (core, "stocklens/core.py"),
                      (paper_rebalance_math, "paper_rebalance_math.py")):
        assert Path(mod.__file__).resolve() == (runtime / path).resolve(), (
            "TEST_NOT_RUNNING_DEPLOYED_MODULE:" + mod.__name__
        )
assert_economic_import_provenance()
print("IMPORTED_ECONOMIC_MODULES_FROM_DOWNLOADED_LAMBDA_ZIP_CONFIRMED", flush=True)
print("TEST_ONLY_TAX_RESEARCH_IMPORTED_FROM_PUBLIC_REPO_NOT_DEPLOYED", flush=True)
import pytest
tests = (
    "tests/test_paper_order_lifecycle_matrix.py",
    "tests/test_signal_to_paper_order_handoff.py",
    "tests/test_paper_execution_contract.py",
    "tests/test_paper_transaction_recovery.py",
    "tests/test_paper_eod_completeness.py",
    "tests/test_paper_session_continuity.py",
    "tests/test_paper_tax_receipts.py",
    "tests/test_paper_portfolio_integrity.py",
)
exit_code = pytest.main(["-q", "--disable-warnings"] +
                        [str(repo / t) for t in tests])
assert_economic_import_provenance()
raise SystemExit(exit_code)
'''


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=("inspect", "force-offline"),
                   default="inspect")
    args = p.parse_args(argv)
    repo = Path(__file__).resolve().parents[2]
    record = {
        "kind": "DEPLOYED_AWS_ST_PAPER_ZIP_PUBLIC_ECONOMIC_MODULE_READBACK",
        "account": ACCOUNT, "region": REGION, "function": NAME,
        "mode": args.mode, "aws_mutations": False,
        "lambda_invocations": False, "broker_orders": False,
        "private_handler_directly_tested": False,
        "paper_or_continuity_s3_written": False,
    }
    try:
        assert_local_pins(repo)
        import boto3
        sdk = boto3.session.Session(region_name=REGION)
        raw, cfg = authenticated_download(sdk.client("sts"), sdk.client("lambda"))
        records, handler = inspect_zip(raw, repo)
        record.update({
            "zip_sha256_matches_aws_configuration": True,
            "lambda_code_sha256_b64": cfg["CodeSha256"],
            "economic_module_parity": records,
            "private_handler": handler,
        })
        all_matches = all(x["matches_tested_code"] for x in records.values())
        if args.mode == "inspect":
            record["status"] = ("DEPLOYED_ECONOMIC_MODULE_SOURCE_PARITY_VERIFIED"
                                if all_matches else
                                "DEPLOYED_CODE_NOT_IDENTICAL_TO_PUBLIC_TESTED_MODULES")
            code = 0 if all_matches else 4
        elif not all_matches:
            record["status"] = "DEVIATING_LAMBDA_SOURCE_STOP_BEFORE_FORCED_TESTS"
            code = 4
        else:
            tests_exit = execute_deployed_economic_module_scenarios(raw, repo)
            record["forced_synthetic_economic_module_test_exit"] = tests_exit
            record["status"] = (
                "DEPLOYED_ECONOMIC_MODULE_104_SCENARIOS_PASS_PRIVATE_HANDLER_NOT_TESTED"
                if tests_exit == 0 else
                "DEPLOYED_ECONOMIC_MODULE_FORCED_TESTS_FAILED")
            code = 0 if tests_exit == 0 else 5
    except Exception as exc:
        msg = str(exc)
        record["status"] = "DEPLOYED_PAPER_ZIP_READBACK_BLOCKED_NOT_ATTESTED"
        record["error_type"] = type(exc).__name__
        record["reason"] = msg[:260]
        code = 3
    print(json.dumps(record, sort_keys=True, indent=2), flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())

"""Offline checks for staged AWS import-only runtime smoke invocation.

They do NOT fetch Yahoo, mutate S3, or require connected AWS credentials.
"""
from __future__ import annotations
import importlib
from pathlib import Path
import subprocess

import pytest

from infra.aws import independent_pipeline
from infra.aws import independent_paper
from infra.aws import independent_orchestrator


SMOKE = {"mode": "STAGING_IMPORT_SMOKE"}


@pytest.mark.parametrize("module,component,env_key", [
    (independent_pipeline, "signal", "STOCKLENS_DATA_BUCKET"),
    (independent_paper, "paper", "STOCKLENS_DATA_BUCKET"),
    (independent_orchestrator, "orchestrator", "SIGNAL_FUNCTION"),
])
def test_handler_smoke_is_read_only_and_runs_without_aws_or_market_calls(
    monkeypatch, module, component, env_key
):
    imports = []
    monkeypatch.setattr(importlib, "import_module", lambda x: imports.append(x))
    monkeypatch.setenv("STOCKLENS_DATA_BUCKET", "private-staging-fixture")
    monkeypatch.setenv("SIGNAL_FUNCTION", "candidate-signal")
    monkeypatch.setenv("PAPER_FUNCTION", "candidate-paper")

    def forbidden(*args, **kwargs):
        raise AssertionError("network, S3 and broker calls forbidden in import-only smoke")

    monkeypatch.setattr(independent_pipeline, "run", forbidden)
    monkeypatch.setattr(independent_paper, "run_paper", forbidden)
    monkeypatch.setattr(independent_orchestrator, "run_orchestrator", forbidden)
    report = module.handler(SMOKE, None)
    assert report == {"status": "STAGING_IMPORT_OK", "component": component,
                      "broker_actions": False, "market_data_written": False}
    assert "boto3" in imports
    if component == "paper":
        assert all(name in imports for name in ("numpy", "pandas", "yfinance",
                                                  "exchange_calendars"))


def test_import_smoke_rejects_missing_bucket_env(monkeypatch):
    monkeypatch.setattr(importlib, "import_module", lambda x: None)
    monkeypatch.delenv("STOCKLENS_DATA_BUCKET", raising=False)
    with pytest.raises(RuntimeError, match="STAGING_BUCKET_ENV_MISSING"):
        independent_paper.handler(SMOKE, None)


def test_smoke_shell_has_no_production_or_s3_mutations():
    path = Path("infra/aws/smoke_independent_staging.sh")
    subprocess.run(["bash", "-n", str(path)], check=True)
    source = path.read_text()
    assert "STAGING_IMPORT_SMOKE" in source
    assert "PASS_STAGING_INFRA_AND_IMPORTS" in source
    assert "UNSAFE_SCHEDULE_STATE" in source
    assert "S3_VERSIONING_NOT_ENABLED" in source
    assert "market_data_written" in source
    assert "stocklens-independent-staging" in source
    assert "aws lambda invoke" in source
    assert "aws s3api put-" not in source
    assert "aws cloudformation delete-stack" not in source
    assert "aws events enable-rule" not in source


def test_deploy_checks_smoke_after_cloudformation_completion():
    source = Path("infra/aws/deploy_independent_staging.sh").read_text()
    assert "bash infra/aws/smoke_independent_staging.sh" in source
    assert source.index("aws cloudformation deploy") < source.index(
        "bash infra/aws/smoke_independent_staging.sh"
    )

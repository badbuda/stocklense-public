"""Offline verification of the staging-only Yahoo network probe and signal acceptance script."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import subprocess

import pytest

from infra.aws import independent_pipeline
from test_aws_independent_pipeline import daily_fixture


def test_probe_reads_yahoo_schema_without_generating_signal(monkeypatch):
    payload, day, clock = daily_fixture()
    calls = []
    monkeypatch.setattr(independent_pipeline, "_vendor_request",
                        lambda *, now: (calls.append(now) or payload, "f" * 64))
    def forbidden(*args, **kwargs):
        raise AssertionError("no staging market signal production is allowed in probe")
    monkeypatch.setattr(independent_pipeline, "run", forbidden)
    result = independent_pipeline.handler({"mode": "STAGING_VENDOR_NETWORK_PROBE"}, None)
    assert len(calls) == 1
    assert result["status"] == "STAGING_VENDOR_NETWORK_OK"
    assert result["component"] == "signal"
    assert result["broker_actions"] is False
    assert result["market_data_written"] is False
    assert result["latest_session_completed"] is False
    assert result["historical_parity_proven"] is False
    assert result["rows"] == 740


def test_probe_rejects_wrong_vendor_or_malformed_price_array():
    payload, day, clock = daily_fixture()
    payload["chart"]["result"][0]["meta"]["symbol"] = "TQQQ"
    with pytest.raises(ValueError, match="VENDOR_PROBE_WRONG_SYMBOL"):
        independent_pipeline._vendor_network_probe(
            now=clock, fetcher=lambda *, now: (payload, "a" * 64))
    payload["chart"]["result"][0]["meta"]["symbol"] = "QQQ"
    payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"].pop()
    with pytest.raises(ValueError, match="VENDOR_PROBE_ARRAY_MISMATCH"):
        independent_pipeline._vendor_network_probe(
            now=clock, fetcher=lambda *, now: (payload, "b" * 64))


def test_probe_rejects_naive_clock():
    with pytest.raises(ValueError, match="NAIVE_VENDOR_PROBE_CLOCK"):
        independent_pipeline._vendor_network_probe(
            now=datetime(2026, 10, 12, 12, 0))


def test_acceptance_shell_is_bash_valid_and_staging_only():
    script = Path("infra/aws/accept_independent_staging.sh")
    subprocess.run(["bash", "-n", str(script)], check=True)
    raw = script.read_text(encoding="utf-8")
    assert "STAGING_VENDOR_NETWORK_PROBE" in raw
    assert "STAGING_ONLY" in raw
    assert "STOP_INCOMPLETE_NY_SESSION" in raw
    assert "STAGING_SIGNAL_AND_S3_RECEIPT_VERIFIED" in raw
    assert "manifest_response_version" in raw
    assert "S3_OBJECT_VERSION_MISSING" in raw
    assert "frozen_feature_window_sha" in raw
    assert "market_data_written" in raw
    assert "aws events enable-rule" not in raw
    assert "aws cloudformation delete-stack" not in raw
    assert "stocklens-paper" not in raw.replace(
        "# Never touches stocklens-paper", ""
    )

"""Read-only prospective AWS Paper preflight; no S3 mutations or broker calls."""
from datetime import datetime, timezone
from dataclasses import replace
import json

import pytest

from infra.aws.independent_paper import (
    preflight_prospective_paper_bootstrap,
)
from test_aws_session_continuity import S3, observed_market, seed

U = lambda y, m, d, h, mi=0: datetime(y, m, d, h, mi, tzinfo=timezone.utc)


def prepared():
    s3 = S3()
    seed(s3, "2026-10-12", "2026-10-12T23:15:00+00:00", U(2026, 10, 12, 23, 20))
    seed(s3, "2026-10-13", "2026-10-13T22:25:00+00:00", U(2026, 10, 13, 22, 30))
    return s3


def preview(s3, at=None, fetch=None):
    return preflight_prospective_paper_bootstrap(
        session="2026-10-13", now=at or U(2026, 10, 13, 23),
        s3=s3, bucket="staging",
        market_fetch=fetch or (lambda previous, day: observed_market(day)),
    )


def test_preflight_computes_valid_first_session_without_any_s3_write():
    s3 = prepared()
    keys, contents, times = set(s3.data), dict(s3.data), dict(s3.mtime)
    result = preview(s3)
    assert result["status"] == "STAGING_PAPER_BOOTSTRAP_PREFLIGHT_PASS_READ_ONLY"
    assert result["session"] == "2026-10-13"
    assert result["prior_session"] == "2026-10-12"
    assert result["market_source"] == "YFINANCE_1M_RAW"
    assert result["paper_accounting_audit"] == "PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS"
    assert len(result["model_candidate_sha256"]) == 64
    assert result["paper_model_equity"] > 0
    assert result["broker_orders"] is False and result["broker_fills"] is False
    assert result["broker_actions"] is False
    assert result["market_data_written"] is False
    assert result["paper_data_written"] is False
    assert result["genesis_written"] is False
    assert result["prospective_bootstrap_authorized"] is False
    assert set(s3.data) == keys and s3.data == contents and s3.mtime == times


def test_preflight_refuses_prior_signal_archived_after_market_open():
    s3 = prepared()
    s3.mtime["signals/2026-10-12.json"] = U(2026, 10, 13, 14)
    with pytest.raises(RuntimeError, match="PRIOR_SIGNAL_NOT_ARCHIVED_BEFORE_OPEN"):
        preview(s3)
    assert not any(k.startswith("paper/") for k in s3.data)


def test_preflight_refuses_current_signal_recorded_before_close():
    s3 = prepared()
    s3.mtime["signals/2026-10-13.json"] = U(2026, 10, 13, 19, 59)
    with pytest.raises(RuntimeError, match="CURRENT_SIGNAL_NOT_ARCHIVED_AFTER_CLOSE"):
        preview(s3)


def test_preflight_requires_both_immutable_s3_signals():
    s3 = prepared()
    del s3.data["signals/2026-10-12.json"]
    with pytest.raises(Exception):
        preview(s3)
    assert not any(k.startswith("paper/") for k in s3.data)


def test_preflight_refuses_existing_genesis_or_continuity():
    s3 = prepared()
    s3.put("paper/book/NEW_AWS_INDEPENDENT_STAGING_BOOK/genesis.json",
           b'{"schema":"FAKE"}', U(2026, 10, 13, 23))
    with pytest.raises(RuntimeError, match="EXISTING_PAPER_BOOK"):
        preview(s3)
    del s3.data["paper/book/NEW_AWS_INDEPENDENT_STAGING_BOOK/genesis.json"]
    s3.put("paper/continuity/2026-10-13.json", b'{"schema":"fake"}', U(2026, 10, 13, 23))
    with pytest.raises(RuntimeError, match="EXISTING_PAPER_CONTINUITY"):
        preview(s3)


def test_preflight_requires_completed_current_session_and_observed_market():
    s3 = prepared()
    with pytest.raises(RuntimeError, match="PREFLIGHT_REQUIRES_COMPLETED_SESSION_BEFORE_NEXT_OPEN"):
        preview(s3, at=U(2026, 10, 13, 19, 59))
    # 08:30 in Israel on Oct 14 is 01:30 NY: next exchange open not reached.
    assert preview(s3, at=U(2026, 10, 14, 5, 30))["status"].endswith("PASS_READ_ONLY")
    # After the next NYSE open this is NOT prospective first-session evidence.
    with pytest.raises(RuntimeError, match="PREFLIGHT_REQUIRES_COMPLETED_SESSION_BEFORE_NEXT_OPEN"):
        preview(s3, at=U(2026, 10, 14, 14))
    with pytest.raises(ValueError, match="UNEXPECTED_OBSERVED_EXECUTION_SOURCE"):
        bad = replace(observed_market("2026-10-13"), source="SYNTHETIC")
        preview(s3, fetch=lambda prior, day: bad)
    assert not any(k.startswith("paper/") for k in s3.data)


def test_read_only_mode_has_no_hidden_write_path():
    from pathlib import Path
    p = Path("infra/aws/independent_paper.py").read_text()
    function = p.split("def preflight_prospective_paper_bootstrap(", 1)[1].split(
        "\ndef _import_smoke():", 1
    )[0]
    assert "_immutable_put(" not in function
    assert "run_paper(" not in function
    assert "build_paper_receipt(" in function
    assert "STAGING_PAPER_BOOTSTRAP_PREFLIGHT" in p


def test_preflight_operator_script_is_read_only_and_region_fenced():
    from pathlib import Path
    import subprocess
    path = Path("infra/aws/accept_independent_paper_preflight.sh")
    script = path.read_text()
    subprocess.run(["bash", "-n", str(path)], check=True)
    assert "STAGING_PAPER_BOOTSTRAP_PREFLIGHT" in script
    assert "REFUSE_NON_STAGING_REGION" in script
    assert "REFUSE_ACTIVE_PAPER_ORCHESTRATOR" in script
    assert "PAPER_BOOTSTRAP_NOT_AUTHORIZED" in script
    for forbidden in (
        "aws s3api put-object", "aws cloudformation deploy", "aws events enable-rule",
        "aws lambda update-function", "aws s3 rm", '"bootstrap":true',
    ):
        assert forbidden not in script

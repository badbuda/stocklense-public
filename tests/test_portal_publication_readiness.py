"""Publication health stays blocked while a stale Paper archive is displayed correctly."""
from datetime import datetime, timezone
from pathlib import Path

import pytest
import portal_publication_readiness as p

NOW=datetime(2026,10,29,21,0,tzinfo=timezone.utc)


def fixture(paper="2026-10-29", signal="2026-10-29", risk="2026-10-29",
            history="2026-10-29", n=5):
    return (
        {"signal":{"asof_date":signal},
         "paper":{"sessions":n,"latest":{"session_date":paper}}},
        {"updated_session":history,"observed_ohlc_available":True},
        {"period":{"end":risk}},
    )


def test_current_matching_static_publication_still_does_not_prove_aws_or_broker():
    d=p.assess(*fixture(),now=NOW)
    assert d["ready"] is True
    assert d["scope"]=="PUBLIC_GITHUB_ARCHIVE_ONLY_NOT_AUTHENTICATED_AWS_ST"
    assert d["broker_fills_certified"] is False
    assert d["aws_st_signal_proven"] is False
    assert d["aws_st_paper_proven"] is False


def test_archived_oct09_paper_blocks_publication_but_not_browser_correctness():
    d=p.assess(*fixture(paper="2026-10-09",signal="2026-10-28"),now=NOW)
    assert d["ready"] is False
    assert any(s.startswith("PUBLISHED_PAPER_ARCHIVE_STALE:paper=2026-10-09")
               for s in d["issues"])
    assert any(s.startswith("STALE_PUBLISHED_DATE:paper:") for s in d["issues"])
    js=Path("tests/portal_browser_smoke.cjs").read_text(encoding="utf-8")
    assert "PORTAL_ARCHIVAL_PAPER_DEGRADED_EXPECTED" in js
    assert "Stale Paper must render a visible error state" in js
    assert "failures.push(reason)" not in js


def test_missing_and_future_dates_block():
    d=p.assess(*fixture(signal=None,paper="2026-10-30"),now=NOW)
    assert d["ready"] is False
    assert "MISSING_OR_INVALID_DATE:signal" in d["issues"]
    assert "FUTURE_PUBLISHED_DATE:paper" in d["issues"]


def test_history_and_risk_must_reconcile():
    d=p.assess(*fixture(history="2026-10-28",risk="2026-10-27"),now=NOW)
    assert "SOURCE_SESSION_MISMATCH:history" in d["issues"]
    assert "SOURCE_SESSION_MISMATCH:risk" in d["issues"]


def test_short_paper_or_unobserved_etf_blocks():
    data,history,risk=fixture(n=1)
    history["observed_ohlc_available"]=False
    d=p.assess(data,history,risk,now=NOW)
    assert "PUBLISHED_PROSPECTIVE_PAPER_TOO_SHORT" in d["issues"]
    assert "OBSERVED_MARKET_DATA_NOT_VERIFIED" in d["issues"]


def test_never_treat_naive_clock_as_valid():
    with pytest.raises(ValueError,match="CLOCK_MUST_BE_TIMEZONE_AWARE"):
        p.assess(*fixture(),now=datetime(2026,10,29))


def test_immutable_market_sources_and_portal_code_are_not_modified():
    source=Path("portal_publication_readiness.py").read_text(encoding="utf-8")
    assert "PUBLIC_GITHUB_ARCHIVE_ONLY_NOT_AUTHENTICATED_AWS_ST" in source
    for danger in (".put_object(", "boto3.client(", ".enable_rule(", ".invoke(",
                   "requests.", "yfinance.", ".execute_change_set("):
        assert danger not in source

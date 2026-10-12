"""Offline tests for staged S3-only producer; no AWS calls."""
from datetime import datetime, timezone
import pytest
from infra.aws.independent_signal_producer import build_signal


def test_rejects_missing_rows():
    with pytest.raises(ValueError, match="REQUIRE_DATE_CLOSE_CSV"):
        build_signal(b"wrong,header\na,b\n", datetime(2026, 10, 12, 23, tzinfo=timezone.utc),
                     source="test", source_sha256="x")


def test_rejects_duplicate_dates():
    raw = b"Date,Close\n" + b"2008-01-02,100\n" * 300
    with pytest.raises(ValueError, match="UNSORTED_DUPLICATE"):
        build_signal(raw, datetime(2026, 10, 12, 23, tzinfo=timezone.utc),
                     source="test", source_sha256="x")

def test_rejects_nonfinite_price():
    from datetime import date, timedelta
    start = date(2008, 1, 2)
    rows = [f"{start + timedelta(days=i)},{100 + i}" for i in range(300)]
    rows[100] = rows[100].split(",")[0] + ",nan"
    raw = ("Date,Close\\n" + "\\n".join(rows) + "\\n").encode()
    with pytest.raises(ValueError, match="INVALID_ADJUSTED_CLOSE"):
        build_signal(raw, datetime(2026, 10, 12, 23, tzinfo=timezone.utc),
                     source="test", source_sha256="x")


def test_frozen_decisions_match_core():
    from datetime import date, timedelta
    from stocklens.core import replay_levels
    start = date(2008, 1, 2)
    dates = [(start + timedelta(days=i)).isoformat() for i in range(700)]
    closes = [100.0 + i / 10 for i in range(700)]
    raw = ("Date,Close\\n" + "\\n".join(
        f"{d},{c}" for d, c in zip(dates, closes)
    ) + "\\n").encode()
    report = build_signal(raw, datetime(2026, 10, 12, 23, tzinfo=timezone.utc),
                          source="test", source_sha256="x")
    expected = replay_levels(closes, dates)
    assert report["latest"] == expected[-1].to_dict()
    assert report["previous"] == expected[-2].to_dict()
    assert report["execution_plan"]["broker_actions_enabled"] is False

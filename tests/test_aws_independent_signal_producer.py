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

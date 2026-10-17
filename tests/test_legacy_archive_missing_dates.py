"""Regression: a missing DynamoDB GetItem row is not a JSON parser exception."""
import subprocess
from unittest.mock import patch
import pytest
from aws_journal_export import get_item

def mock_result(data):
    return subprocess.CompletedProcess([], 0, data, "")

def test_absent_getitem_is_reported_as_missing_not_fabricated():
    for payload in ("", "   ", "{}"):
        with patch("aws_journal_export.subprocess.run",return_value=mock_result(payload)):
            assert get_item("journal","2026-10-12") is None

def test_corrupt_getitem_is_rejected():
    for payload in ("{broken", "[]", '{"Item":42}', "null"):
        with patch("aws_journal_export.subprocess.run",return_value=mock_result(payload)):
            with pytest.raises((ValueError,TypeError)):
                get_item("journal","2026-10-12")

def test_legacy_browser_scans_7_known_sessions_not_2_stale_dates():
    from pathlib import Path
    src=Path("docs/portal-cloud.js").read_text(encoding="utf-8")
    for day in ("2026-10-08","2026-10-09","2026-10-12",
                "2026-10-13","2026-10-14","2026-10-15","2026-10-16"):
        assert day in src
    assert "LEGACY_INCIDENT_SESSIONS" in src
    assert "INCOMPLETE_OR_MISORDERED_LEGACY_ARCHIVE_REPLY" in src
    assert "days=h?.daily?" not in src

def test_legacy_cloudwatch_audit_uses_nyse_session_gate():
    from pathlib import Path
    s=Path(".github/workflows/aws-shadow-journal-audit.yml").read_text()
    assert 'session="${{ steps.market_calendar.outputs.session }}"' in s
    assert "TZ=America/New_York date -d yesterday" not in s
    assert "LEGACY_SIGNAL_ARCHIVE_MISSING:" in s
    assert "LEGACY_PAPER_ARCHIVE_MISSING:" in s

"""Regression: missing DynamoDB keys must never be fabricated as evidence."""
from unittest.mock import patch
import subprocess
import pytest
from aws_journal_export import get_item

def test_empty_cli_stdout_is_missing():
    with patch("aws_journal_export.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "", "")):
        assert get_item("table", "2026-10-12") is None

def test_empty_object_is_missing():
    with patch("aws_journal_export.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "{}", "")):
        assert get_item("table", "2026-10-12") is None

def test_malformed_nonempty_json_fails_closed():
    with patch("aws_journal_export.subprocess.run", return_value=subprocess.CompletedProcess([], 0, "{broken", "")):
        with pytest.raises(ValueError):
            get_item("table", "2026-10-12")

def test_nonobject_and_invalid_item_fail_closed():
    for payload in ('[]', '{"Item":42}'):
        with patch("aws_journal_export.subprocess.run", return_value=subprocess.CompletedProcess([], 0, payload, "")):
            with pytest.raises(ValueError):
                get_item("table", "2026-10-12")

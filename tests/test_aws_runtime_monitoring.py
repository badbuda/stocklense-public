"""Offline read-only monitoring checks."""
import pytest
from aws_runtime_watchdog import WatchdogError, inspect

def test_invalid_stack_name():
    with pytest.raises(ValueError, match="INVALID_STACK_NAME"):
        inspect("invalid stack name", lambda _: {})

def test_missing_stack_resource():
    with pytest.raises(KeyError):
        inspect("stocklens-paper", lambda _: {})

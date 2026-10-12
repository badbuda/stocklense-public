"""Offline unit tests for AWS-only disabled-by-default orchestration."""
from datetime import datetime, timezone
import io
import json

import pytest

from infra.aws.independent_orchestrator import (
    current_completed_session, run_orchestrator
)


class FakeLambda:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def invoke(self, **kwargs):
        event = json.loads(kwargs["Payload"])
        self.calls.append((kwargs["FunctionName"], event))
        if self.fail:
            return {"StatusCode": 200, "FunctionError": "Unhandled",
                    "Payload": io.BytesIO(b'{"errorMessage":"FAIL"}')}
        status = ("STAGED_SIGNAL_ARCHIVED" if kwargs["FunctionName"] == "signal"
                  else "STAGED_PAPER_VERIFIED")
        result = {"status": status, "session": event["expected_session"],
                  "broker_actions": False, "broker_orders": False,
                  "broker_fills": False,
                  "signal_sha256": "a" * 64, "paper_sha256": "b" * 64}
        return {"StatusCode": 200,
                "Payload": io.BytesIO(json.dumps(result).encode())}


def test_disabled_rule_session_resolver_dst_and_holiday():
    # 00:10Z Tuesday = Monday after 20:00 EDT, after completed close.
    assert current_completed_session(
        datetime(2026, 10, 13, 0, 10, tzinfo=timezone.utc)
    ) == "2026-10-12"
    # 00:10Z Saturday, Christmas 2026 Friday is an XNYS holiday.
    assert current_completed_session(
        datetime(2026, 12, 26, 0, 10, tzinfo=timezone.utc)
    ) is None


def test_orchestrator_sequences_signal_then_paper_and_never_bootstraps():
    client = FakeLambda()
    response = run_orchestrator(
        now=datetime(2026, 10, 13, 0, 10, tzinfo=timezone.utc),
        client=client, signal_function="signal", paper_function="paper"
    )
    assert response["status"] == "STAGED_DAILY_COMPLETED"
    assert response["broker_actions"] is False
    assert len(client.calls) == 2
    assert [x[0] for x in client.calls] == ["signal", "paper"]
    assert client.calls[0][1]["mode"] == "STAGING_ONLY"
    assert client.calls[1][1]["mode"] == "STAGING_PAPER_ONLY"
    assert client.calls[1][1]["bootstrap"] is False


def test_orchestrator_fails_closed_on_failed_signal():
    client = FakeLambda(fail=True)
    with pytest.raises(RuntimeError, match="CANDIDATE_LAMBDA_FAILED"):
        run_orchestrator(
            now=datetime(2026, 10, 13, 0, 10, tzinfo=timezone.utc),
            client=client, signal_function="signal", paper_function="paper"
        )
    assert len(client.calls) == 1


def test_too_early_session_rejected():
    with pytest.raises(RuntimeError, match="MARKET_DAY_NOT_YET_COMPLETE"):
        current_completed_session(
            datetime(2026, 10, 12, 19, 0, tzinfo=timezone.utc)
        )

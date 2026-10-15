"""Fail-closed AWS candidate orchestrator: completed NYSE session -> Signal -> Paper.

No GitHub; no broker; cannot bootstrap a paper account. The associated
EventBridge rule is present but DISABLED until independent parity and an
explicitly approved prospective Paper starting book are verified.
"""
from __future__ import annotations

from datetime import datetime, time, timezone
import json
import os
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def current_completed_session(now: datetime) -> str | None:
    if now.tzinfo is None:
        raise ValueError("NAIVE_ORCHESTRATOR_CLOCK")
    ny = now.astimezone(NY)
    if ny.time() < time(18, 0):
        raise RuntimeError("MARKET_DAY_NOT_YET_COMPLETE")
    import exchange_calendars as xcals
    day = ny.date().isoformat()
    cal = xcals.get_calendar("XNYS")
    if not cal.is_session(day):
        return None
    return day


BROKER_FLAGS = ("broker_actions", "broker_orders", "broker_fills")


def _assert_no_broker_activity(result: dict, required=("broker_actions",)) -> None:
    """Fail closed on ANY broker flag that is not literally False, and require the
    flags each component contract promises. (Previously a response with
    broker_actions=true passed whenever broker_orders was False.)"""
    for key in BROKER_FLAGS:
        if key in result and result[key] is not False:
            raise RuntimeError("UNSAFE_CANDIDATE_RESPONSE:" + key)
    for key in required:
        if result.get(key) is not False:
            raise RuntimeError("UNSAFE_CANDIDATE_RESPONSE:MISSING_" + key)


def _invoke(client, function: str, event: dict, required_status, required_flags) -> dict:
    response = client.invoke(
        FunctionName=function,
        InvocationType="RequestResponse",
        Payload=json.dumps(event, separators=(",", ":")).encode(),
    )
    if response.get("StatusCode") != 200 or response.get("FunctionError"):
        # Do not log full payloads or sensitive provider failures by default.
        raise RuntimeError("CANDIDATE_LAMBDA_FAILED:" + function)
    payload = response["Payload"].read(100_001)
    if len(payload) > 100_000:
        raise RuntimeError("CANDIDATE_RESPONSE_TOO_LARGE")
    result = json.loads(payload)
    _assert_no_broker_activity(result, required_flags)
    allowed = (required_status,) if isinstance(required_status, str) else tuple(required_status)
    if result.get("status") not in allowed or result.get("session") != event["expected_session"]:
        raise RuntimeError("CANDIDATE_RESPONSE_SESSION_OR_STATUS_MISMATCH")
    return result


def run_orchestrator(*, now: datetime, client, signal_function: str, paper_function: str):
    session = current_completed_session(now)
    if session is None:
        return {"status": "SKIPPED_XNYS_NONTRADING_DAY", "broker_actions": False}
    if signal_function == paper_function or not signal_function or not paper_function:
        raise ValueError("TWO_DISTINCT_LAMBDAS_REQUIRED")
    first = _invoke(client, signal_function,
                    {"mode": "STAGING_ONLY", "expected_session": session},
                    "STAGED_SIGNAL_ARCHIVED", ("broker_actions",))
    # Catch-up processes every unrecorded session (bounded horizon) oldest-first and
    # classifies each; it can never bootstrap or reset the book.
    second = _invoke(client, paper_function,
                     {"mode": "STAGING_PAPER_CATCHUP", "expected_session": session,
                      "bootstrap": False},
                     ("STAGED_PAPER_CATCHUP_COMPLETED", "STAGED_PAPER_HALTED"),
                     BROKER_FLAGS)
    if second["status"] == "STAGED_PAPER_HALTED":
        # The MISSED record is already persisted; surface as an invocation failure so
        # OnFailure/alarm routing fires instead of a silent success.
        raise RuntimeError("PAPER_BOOK_HALTED_MISSED_SESSION:" + json.dumps(second.get("sessions", [])))
    return {
        "status": "STAGED_DAILY_COMPLETED",
        "session": session,
        "signal_sha256": first["signal_sha256"],
        "paper_sha256": second["paper_sha256"],
        "paper_sessions": second.get("sessions", []),
        "broker_actions": False,
        "broker_orders": False,
        "broker_fills": False,
    }


def _import_smoke():
    import importlib
    for package in ("exchange_calendars", "boto3"):
        importlib.import_module(package)
    if not os.environ.get("SIGNAL_FUNCTION") or not os.environ.get("PAPER_FUNCTION"):
        raise RuntimeError("STAGING_CHILD_LAMBDAS_ENV_MISSING")
    return {"status": "STAGING_IMPORT_OK", "component": "orchestrator",
            "broker_actions": False, "market_data_written": False}


def handler(event, context):
    if event.get("mode") == "STAGING_IMPORT_SMOKE":
        return _import_smoke()
    import boto3
    if event.get("mode") != "STAGING_ORCHESTRATOR_ONLY":
        raise RuntimeError("ORCHESTRATOR_STAGING_MODE_REQUIRED")
    return run_orchestrator(
        now=datetime.now(timezone.utc), client=boto3.client("lambda"),
        signal_function=os.environ["SIGNAL_FUNCTION"],
        paper_function=os.environ["PAPER_FUNCTION"],
    )

"""Read-only AWS staging status for explicitly supplied XNYS trading dates.

No implicit backfill, no Lambda invoke, no S3 writes, no clock re-baselining.
This is an operator diagnostic, NOT a proof of on-time scheduled execution:
a manual source-pinned Signal receipt also qualifies as a receipt.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

STACK = "stocklens-independent-staging"
REGION = "eu-central-1"
ACCOUNT = "634740393398"
EXPECTED_SIGNAL = "cron(30 2 ? * TUE-SAT *)"
EXPECTED_PAPER = "cron(20 3 ? * TUE-SAT *)"
DEADLINE = time(3, 30, tzinfo=timezone.utc)
SESSION_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class StagingDiagnosticError(RuntimeError):
    pass


def _call_aws(*args: str) -> dict:
    command = ["aws", "--region", REGION, *args, "--output", "json"]
    result = subprocess.run(command, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        # Never print CLI stderr: it might contain account/user path details.
        raise StagingDiagnosticError("AWS_READ_FAILED:" + ":".join(args[:2]))
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise StagingDiagnosticError("MALFORMED_AWS_RESPONSE") from exc
    if not isinstance(value, dict):
        raise StagingDiagnosticError("EXPECTED_AWS_JSON_OBJECT")
    return value


def _read_versioned_signal(bucket: str, session: str, version: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="stocklens-readonly-") as directory:
        dest = Path(directory) / "signal.json"
        args = ["aws", "--region", REGION, "s3api", "get-object",
                "--bucket", bucket, "--key", f"signals/{session}.json",
                "--version-id", version, str(dest), "--output", "json"]
        result = subprocess.run(args, capture_output=True, check=False)
        if result.returncode:
            raise StagingDiagnosticError("SIGNAL_VERSIONED_READ_FAILED:" + session)
        raw = dest.read_bytes()
    if len(raw) > 200_000:
        raise StagingDiagnosticError("SIGNAL_OBJECT_TOO_LARGE:" + session)
    return raw


def _utc(value: str) -> datetime:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            raise ValueError("timezone absent")
    except (TypeError, ValueError, AttributeError) as exc:
        raise StagingDiagnosticError("BAD_S3_SERVER_TIME") from exc
    return stamp.astimezone(timezone.utc)


def _valid_signal(data: dict, session: str) -> bool:
    if not isinstance(data, dict):
        return False
    return (
        data.get("mode") == "SHADOW_ONLY_NO_BROKER_ACTIONS"
        and data.get("signal_source") == "QQQ_ADJUSTED_DAILY_CLOSE"
        and data.get("latest", {}).get("asof_date") == session
        and data.get("data_audit", {}).get("last_completed_date") == session
        and data.get("execution_plan", {}).get("broker_actions_enabled") is False
        and data.get("data_audit", {}).get("source") == "YFINANCE_QQQ_AUTO_ADJUSTED"
    )


def _session_status(*, now: datetime, session: str, bucket: str, head: dict | None,
                    read_signal=_read_versioned_signal) -> dict:
    deadline = datetime.combine(date.fromisoformat(session) + timedelta(days=1), DEADLINE)
    base = {"session": session, "deadline_utc": deadline.isoformat()}
    if head is None:
        return {**base, "status": "NOT_DUE_NO_RECEIPT" if now < deadline else "MISSING_DUE_RECEIPT"}
    saved, version = _utc(head.get("LastModified")), head.get("VersionId")
    if not version or version == "null":
        return {**base, "status": "INVALID_UNVERSIONED_RECEIPT"}
    try:
        raw = read_signal(bucket, session, version)
        payload = json.loads(raw)
    except (StagingDiagnosticError, ValueError, TypeError) as exc:
        return {**base, "status": "INVALID_UNREADABLE_RECEIPT", "error": type(exc).__name__}
    if not _valid_signal(payload, session):
        return {**base, "status": "INVALID_SIGNAL_CONTRACT"}
    # S3 server timestamp is authoritative. No attempt to rewrite a missed
    # deadline, or to claim that receipt provenance proves EventBridge delivery.
    status = "VERIFIED_RECEIPT_ON_TIME" if saved <= deadline else "VERIFIED_RECEIPT_LATE"
    return {**base, "status": status, "s3_saved_at_utc": saved.isoformat(),
            "s3_version_id": version, "sha256": hashlib.sha256(raw).hexdigest(),
            "scheduled_execution_proven": False}


def _session_head(bucket: str, session: str) -> dict | None:
    result = subprocess.run(
        ["aws", "--region", REGION, "s3api", "head-object", "--bucket", bucket,
         "--key", f"signals/{session}.json", "--output", "json"],
        capture_output=True, text=True, check=False,
    )
    if result.returncode:
        if "404" in result.stderr or "Not Found" in result.stderr or "NoSuchKey" in result.stderr:
            return None
        raise StagingDiagnosticError("SIGNAL_HEAD_READ_FAILED:" + session)
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise StagingDiagnosticError("BAD_SIGNAL_HEAD_RESPONSE:" + session) from exc


def snapshot(sessions: list[str], *, now: datetime,
             aws=_call_aws, head=_session_head, read_signal=_read_versioned_signal) -> dict:
    if now.tzinfo is None:
        raise StagingDiagnosticError("NAIVE_OPERATOR_CLOCK")
    if not sessions:
        raise StagingDiagnosticError("AT_LEAST_ONE_SESSION_REQUIRED")
    for session in sessions:
        if not SESSION_PATTERN.fullmatch(session):
            raise StagingDiagnosticError("BAD_SESSION_FORMAT")
        d = date.fromisoformat(session)
        if d.weekday() > 4:
            raise StagingDiagnosticError("SESSION_IS_WEEKEND")
    account = aws("sts", "get-caller-identity").get("Account")
    if account != ACCOUNT:
        raise StagingDiagnosticError("WRONG_AWS_ACCOUNT")
    stack = aws("cloudformation", "describe-stacks", "--stack-name", STACK)["Stacks"][0]
    outputs = {row["OutputKey"]: row["OutputValue"] for row in stack["Outputs"]}
    bucket = outputs["CandidateDataBucket"]
    rules = {}
    for key, expected_state, expected_schedule in (
        ("CandidateSignalOnlyRuleName", "ENABLED", EXPECTED_SIGNAL),
        ("CandidatePaperOnlyRuleName", "DISABLED", EXPECTED_PAPER),
        ("CandidateOrchestratorRuleName", "DISABLED", "cron(10 0 ? * TUE-SAT *)"),
    ):
        record = aws("events", "describe-rule", "--name", outputs[key])
        rules[key] = {"state": record.get("State"), "schedule": record.get("ScheduleExpression"),
                      "verified": record.get("State") == expected_state and
                                  record.get("ScheduleExpression") == expected_schedule}
    lamb = aws("lambda", "get-function-configuration",
               "--function-name", STACK + "-candidate")
    infra_verified = (
        stack["StackStatus"] == "UPDATE_COMPLETE"
        and all(r["verified"] for r in rules.values())
        and lamb.get("State") == "Active"
        and lamb.get("LastUpdateStatus") == "Successful"
    )
    results = [_session_status(now=now.astimezone(timezone.utc), session=d,
                               bucket=bucket, head=head(bucket, d), read_signal=read_signal)
               for d in sessions]
    due_failures = {
        "MISSING_DUE_RECEIPT", "VERIFIED_RECEIPT_LATE",
        "INVALID_UNVERSIONED_RECEIPT", "INVALID_UNREADABLE_RECEIPT",
        "INVALID_SIGNAL_CONTRACT",
    }
    if not infra_verified:
        readiness = "INFRA_NOT_VERIFIED"
    elif any(r["status"] in due_failures for r in results):
        readiness = "FAIL_CLOSED_SIGNAL_EVIDENCE"
    elif any(r["status"] == "NOT_DUE_NO_RECEIPT" for r in results):
        readiness = "WAITING_FOR_RECEIPT_DEADLINE"
    else:
        readiness = "RECEIPTS_ON_TIME_SCHEDULE_AND_VENDOR_UNPROVEN"
    return {
        "status": readiness,
        "stack": STACK, "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
        "rules": rules, "signal_lambda_state": lamb.get("State"),
        "signal_lambda_update": lamb.get("LastUpdateStatus"),
        "receipts": results,
        "missing_history_not_repaired": True, "broker_orders_authorized": False,
        "paper_automation_verified": False,
        "notice": "Head + versioned JSON checks are NOT provider parity, scheduler provenance, or Paper accounting.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", action="append", required=True,
                        help="Explicit YYYY-MM-DD XNYS session; no holiday inference")
    args = parser.parse_args()
    try:
        result = snapshot(args.session, now=datetime.now(timezone.utc))
    except (StagingDiagnosticError, KeyError, IndexError, ValueError) as exc:
        print(json.dumps({"status": "FAIL_CLOSED", "code": str(exc)[:200]}, sort_keys=True))
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    # The CLI is safe for automation: a successfully rendered report is NOT
    # an all-clear if a due receipt is missing/late or any validation failed.
    return 0 if result["status"] == "RECEIPTS_ON_TIME_SCHEDULE_AND_VENDOR_UNPROVEN" else 2


if __name__ == "__main__":
    raise SystemExit(main())

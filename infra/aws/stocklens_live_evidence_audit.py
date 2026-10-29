#!/usr/bin/env python3
"""Read-only evidence drill across actual deployed StockLens AWS stacks.

Requires AWS CLI, account 634740393398, Frankfurt. No Lambda invocation,
no S3 mutation, EventBridge mutation, brokerage, IAM or CloudFormation update.
Never treats GitHub Shadow data as evidence of an AWS Paper receipt.
"""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import sys
import argparse

ACCOUNT = "634740393398"
REGION = "eu-central-1"
NEW = ["stocklens-st", "stocklens-prod", "stocklens-independent-staging"]
OLD = "stocklens-paper"
SIGNAL_KEYS = ("CandidateSignalOnlyRuleName", "CandidatePaperOnlyRuleName",
               "CandidateOrchestratorRuleName")
LAMBDAS = ("CandidateFunctionName", "CandidatePaperFunctionName",
           "CandidateOrchestratorFunctionName")
MISSING = {"NoSuchKey", "NotFound", "404"}


def cli(service: str, operation: str, *args: str) -> dict:
    # One hard-coded AWS read-only allowlist; no shell invocation.
    allowed = {
        ("sts", "get-caller-identity"),
        ("cloudformation", "describe-stacks"),
        ("cloudformation", "describe-stack-resource"),
        ("events", "describe-rule"),
        ("lambda", "get-function-configuration"),
        ("s3api", "head-object"),
        ("s3api", "get-object"),
        ("logs", "filter-log-events"),
        ("dynamodb", "get-item"),
        ("cloudwatch", "describe-alarms"),
    }
    if (service, operation) not in allowed:
        raise RuntimeError("FORBIDDEN_AWS_ACTION:" + service + "/" + operation)
    p = subprocess.run(
        ["aws", "--region", REGION, "--no-cli-pager", "--output", "json",
         service, operation, *args],
        check=False, text=True, capture_output=True, timeout=65,
    )
    if p.returncode:
        msg = p.stderr.strip()
        raise RuntimeError(f"AWS_READ_FAILED:{service}/{operation}:{msg[:260]}")
    try:
        return json.loads(p.stdout)
    except ValueError as exc:
        raise RuntimeError("AWS_INVALID_JSON:" + service + "/" + operation) from exc


def observed(call, *args):
    try:
        return call(*args)
    except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return {"read_error": str(exc)[:350]}


def get_stack(name: str) -> dict:
    obj = cli("cloudformation", "describe-stacks", "--stack-name", name)
    stacks = obj.get("Stacks") or []
    if len(stacks) != 1:
        raise RuntimeError("STACK_NOT_UNIQUE:" + name)
    st = stacks[0]
    return {"status": st.get("StackStatus"),
            "outputs": {v["OutputKey"]: v["OutputValue"] for v in st.get("Outputs", [])}}


def head(bucket: str, key: str):
    try:
        o = cli("s3api", "head-object", "--bucket", bucket, "--key", key)
        return {
            "status": "PRESENT",
            "version_id": o.get("VersionId"),
            "last_modified": o.get("LastModified"),
            "size": o.get("ContentLength"),
        }
    except RuntimeError as exc:
        # S3 HeadObject often says '404 Not Found' or '403 Forbidden'.
        # A 403 is NEVER interpreted as an absent receipt.
        msg = str(exc)
        if "404" in msg or "Not Found" in msg or "NoSuchKey" in msg:
            return {"status": "MISSING"}
        return {"status": "READ_ERROR", "detail": msg}


def logs(fn: str, session: str):
    """Read bounded *complete* CloudWatch pages and retain actual app messages.

    AWS filter-log-events can paginate; an unpaginated 35-event sample is NOT
    evidence that a particular Lambda logged no error. We keep both application
    messages and a count of runtime START/END/REPORT/INIT events, with no mutating
    CloudWatch actions. Truncation is disclosed rather than hidden.
    """
    day = date.fromisoformat(session)
    start = int(datetime(day.year, day.month, day.day,
                         tzinfo=timezone.utc).timestamp() * 1000)
    end = start + 2 * 86400 * 1000
    seen = set()
    token = None
    events = []
    page_count = 0
    more = False
    try:
        while page_count < 8:
            args = [
                "--log-group-name", "/aws/lambda/" + fn,
                "--start-time", str(start), "--end-time", str(end),
                "--limit", "200",
            ]
            if token is not None:
                args.extend(["--next-token", token])
            response = cli("logs", "filter-log-events", *args)
            page_count += 1
            for event in response.get("events", []):
                event_id = event.get("eventId")
                if event_id is not None and event_id in seen:
                    continue
                if event_id is not None:
                    seen.add(event_id)
                events.append(event)
            next_token = response.get("nextToken")
            if not next_token or next_token == token:
                token = None
                more = False
                break
            token = next_token
            more = True
        formatted = [
            {
                "timestamp": datetime.fromtimestamp(
                    e["timestamp"] / 1000, timezone.utc
                ).isoformat(),
                "message": str(e.get("message", ""))[:900],
            }
            for e in sorted(events, key=lambda e: (e.get("timestamp", 0), e.get("eventId", "")))
        ]
        noise_prefixes = ("START RequestId", "END RequestId", "REPORT RequestId",
                          "INIT_START", "INIT_REPORT", "EXTENSION")
        application = [
            x for x in formatted
            if not x["message"].lstrip().startswith(noise_prefixes)
        ]
        patterns = ("error", "exception", "failed", "runtimeerror",
                    "traceback", "nosuchkey", "missing_", "stale", "denied", "halted")
        alerts = [
            x for x in application
            if any(p in x["message"].lower() for p in patterns)
        ]
        return {
            "status": "EVENTS_PRESENT" if events else "NO_LOG_EVENTS_IN_WINDOW",
            "window_utc": [
                datetime.fromtimestamp(start / 1000, timezone.utc).isoformat(),
                datetime.fromtimestamp(end / 1000, timezone.utc).isoformat()
            ],
            "events_returned": len(events),
            "pages_read": page_count,
            "has_more_pages": more,
            "truncated": more,
            "application_events_count": len(application),
            "potential_error_events_count": len(alerts),
            "last_events": application[-40:],
            "potential_error_events": alerts[-15:],
            "runtime_event_tail": formatted[-8:],
            "note": "Application logs exclude START/END/REPORT/INIT. If truncated, absence of an error is not proven.",
        }
    except RuntimeError as exc:
        return {"status": "LOGS_UNREADABLE", "detail": str(exc)}


def verify_signal(bucket: str, session: str):
    """Only read the original S3 objects; verify market bytes and report binding."""
    required = {
        "market": f"market/qqq/{session}.csv",
        "manifest": f"manifests/qqq/{session}.json",
        "signal": f"signals/{session}.json",
    }
    data = {}
    try:
        with tempfile.TemporaryDirectory(prefix="stocklens-evidence-") as d:
            for name, key in required.items():
                dest = Path(d) / name
                meta = cli("s3api", "get-object", "--bucket", bucket, "--key", key,
                           str(dest))
                raw = dest.read_bytes()
                if not meta.get("VersionId") or meta["VersionId"] == "null":
                    raise RuntimeError("S3_VERSION_ID_MISSING:" + name)
                if len(raw) > 4_000_000:
                    raise RuntimeError("S3_RECEIPT_OVERSIZE:" + name)
                data[name] = {"raw": raw, "sha256": hashlib.sha256(raw).hexdigest(),
                              "version": meta["VersionId"], "key": key}
        signal, manifest = json.loads(data["signal"]["raw"]), json.loads(data["manifest"]["raw"])
        if (signal.get("mode") != "SHADOW_ONLY_NO_BROKER_ACTIONS"
            or signal.get("latest", {}).get("asof_date") != session
            or signal.get("execution_plan", {}).get("broker_actions_enabled") is not False
            or signal.get("data_audit", {}).get("source_sha256") != data["market"]["sha256"]
            or manifest.get("input_key") != data["market"]["key"]
            or manifest.get("input_version_id") != data["market"]["version"]
            or manifest.get("sha256") != data["market"]["sha256"]
            or manifest.get("provider") != "YFINANCE_QQQ_AUTO_ADJUSTED"
            or manifest.get("status") != "VERIFIED"):
            raise RuntimeError("SIGNAL_MARKET_MANIFEST_PROVENANCE_MISMATCH")
        return {
            "status": "S3_SIGNAL_MARKET_MANIFEST_SHA_AND_VERSION_PASS",
            "session": session,
            "level": signal["latest"]["level"],
            "action": signal.get("action"),
            "target_leverage": signal["latest"]["target_leverage"],
            "signal_created_at_utc": signal["generated_at_utc"],
            "source": "AWS_STORED_SHADOW_NOT_BROKER_FILL",
            "market_sha256": data["market"]["sha256"],
            "signal_sha256": data["signal"]["sha256"],
            "s3_version_ids": {k: x["version"] for k, x in data.items()},
            "independent_provider_parity": "NOT_PROVEN",
            "broker_fills_observed": False,
        }
    except (RuntimeError, OSError, ValueError, KeyError, TypeError) as exc:
        return {"status": "NOT_VERIFIED", "reason": str(exc)[:350]}


def ddb(table: str, day: str, *, client=None):
    """Strongly consistent point reads through boto3, never DynamoDB Scan.

    The AWS CLI can render an absent GetItem as an empty stdout, which is
    not JSON. The old audit wrongly labeled that AWS_INVALID_JSON. boto3
    returns a structured response, with no Item when the key is absent.
    Neither absence nor permission errors are confused with one another.
    No full items or confidential payloads are printed.
    """
    if client is None:
        import boto3
        client = boto3.client("dynamodb", region_name=REGION)
    rows = {}
    for suffix in ("", "#PAPER"):
        key = day + suffix
        try:
            obj = client.get_item(
                TableName=table,
                Key={"session_date": {"S": key}},
                ConsistentRead=True,
            )
            if obj.get("ResponseMetadata", {}).get("HTTPStatusCode") != 200:
                raise RuntimeError("DYNAMODB_HTTP_NOT_200")
            item = obj.get("Item")
            if item is None:
                rows[key] = {"status": "MISSING", "read_confirmed": True}
            elif isinstance(item, dict):
                rows[key] = {
                    "status": "PRESENT", "read_confirmed": True,
                    "fields": sorted(item.keys()),
                    "paper_sha256": item.get("paper_sha256", {}).get("S"),
                    "signal_sha256": item.get("signal_sha256", {}).get("S"),
                }
            else:
                rows[key] = {"status": "INVALID_ITEM", "read_confirmed": False}
        except Exception as exc:
            # Include only service error code and exception type, never item data.
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            rows[key] = {
                "status": "READ_ERROR", "read_confirmed": False,
                "error_code": str(code or type(exc).__name__),
            }
    return rows


def audit(session: str):
    if cli("sts", "get-caller-identity").get("Account") != ACCOUNT:
        raise RuntimeError("WRONG_AWS_ACCOUNT_STOP")
    report = {
        "kind": "STOCKLENS_AWS_READ_ONLY_SESSION_EVIDENCE",
        "session": session,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "account_verified": True, "region": REGION,
        "environment": {},
        "aws_mutations": False, "lambda_invocations": False,
        "broker_orders": False, "history_backfilled": False,
    }
    for stack_name in NEW:
        out = observed(get_stack, stack_name)
        if "read_error" in out:
            report["environment"][stack_name] = out
            continue
        keys = out["outputs"]
        data = {"stack_status": out["status"], "bucket": keys.get("CandidateDataBucket")}
        data["rules"] = {
            logical: observed(lambda key: cli("events", "describe-rule",
                     "--name", keys[key]).get("State"), logical)
            for logical in SIGNAL_KEYS if logical in keys
        }
        data["receipts"] = {}
        if keys.get("CandidateDataBucket"):
            for prefix in ("signals/", "paper/sessions/", "paper/continuity/"):
                data["receipts"][prefix + session + ".json"] = head(keys["CandidateDataBucket"], prefix + session + ".json")
            data["activation_anchor"] = head(keys["CandidateDataBucket"],
                                             "monitoring/signal-only-activation.json")
        data["lambda_logs"] = {
            logical: logs(keys[logical], session)
            for logical in LAMBDAS if logical in keys
        }
        if stack_name in ("stocklens-st", "stocklens-independent-staging") and data.get("bucket"):
            data["signal_s3_sha_check"] = verify_signal(data["bucket"], session)
        report["environment"][stack_name] = data
    old = observed(get_stack, OLD)
    if "read_error" not in old:
        data = {"stack_status": old["status"], "table": old["outputs"].get("TableName")}
        if data["table"]:
            data["historical_dynamodb"] = ddb(data["table"], session)
        data["retired_lambda_logs"] = {
            "shadow": logs(OLD + "-shadow", session),
            "paper_evidence": logs(OLD + "-paper-evidence", session),
        }
        report["environment"][OLD] = data
    else:
        report["environment"][OLD] = old
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--session", default="2026-10-28", help="XNYS session YYYY-MM-DD")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    if date.fromisoformat(args.session).isoformat() != args.session:
        raise SystemExit("INVALID_SESSION_DATE")
    try:
        result = audit(args.session)
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc),
                          "aws_mutations": False}, ensure_ascii=False))
        return 2
    txt = json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True)
    print(txt)
    if args.output:
        args.output.write_text(txt + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

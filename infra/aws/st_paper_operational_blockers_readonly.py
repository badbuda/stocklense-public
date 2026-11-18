#!/usr/bin/env python3
"""Authenticate and report ALL ST Paper operational blockers; read only.

This is a diagnostic, NEVER a recovery/green attestation. The separate
st_paper_closeout_readonly.py remains the strict fail-closed acceptance gate.
No Lambda invokes, no AWS writes, no alarm acknowledgements, no broker calls.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
import sys

ACCOUNT = "634740393398"
REGION = "eu-central-1"
ST = "stocklens-st"
PROD = "stocklens-prod"
BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
PROD_BUCKET = "stocklens-prod-candidatedata-c3yge4ymwb7u"
ALARM_PREFIX = "stocklens-st"
RULE_KEYS = ("CandidateSignalOnlyRuleName", "CandidatePaperOnlyRuleName",
             "CandidateOrchestratorRuleName")
EXPECTED_ST_CRON = (
    "cron(30 5,8,11,12 ? * TUE-SAT *)",
    "cron(0 13 ? * TUE-SAT *)",
    "cron(10 0 ? * TUE-SAT *)",
)
EXPECTED_PROD_CRON = (
    "cron(30 2 ? * TUE-SAT *)",
    "cron(20 3 ? * TUE-SAT *)",
    "cron(10 0 ? * TUE-SAT *)",
)


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def outputs(cf, stack_name):
    rows = cf.describe_stacks(StackName=stack_name)["Stacks"]
    require(len(rows) == 1 and rows[0]["StackStatus"] in
            ("CREATE_COMPLETE", "UPDATE_COMPLETE"), "UNSTABLE_STACK:" + stack_name)
    return {r["OutputKey"]: r["OutputValue"] for r in rows[0].get("Outputs", [])}


def object_status(s3, key):
    """Inspect version and safe metadata, never expose holdings/P&L/positions."""
    try:
        item = s3.get_object(Bucket=BUCKET, Key=key)
    except Exception as exc:
        err = str((getattr(exc, "response", {}) or {}).get("Error", {}).get("Code", ""))
        if err in ("NoSuchKey", "404", "NotFound"):
            return {"status": "MISSING_VERIFIED"}
        return {"status": "UNVERIFIED_READ_ERROR", "error_code": err or type(exc).__name__}
    try:
        version = item.get("VersionId")
        length = item.get("ContentLength")
        require(isinstance(version, str) and version not in ("", "null") and
                type(length) is int and 2 <= length <= 2_000_000,
                "OBJECT_VERSION_OR_SIZE_INVALID")
        # Read only enough to verify that this S3 object is structurally JSON,
        # without logging sensitive Paper economic state.
        raw = item["Body"].read(2_000_001)
        require(len(raw) == length and isinstance(json.loads(raw), dict),
                "OBJECT_BYTES_NOT_VERIFIABLE")
        return {"status": "VERSIONED_JSON_PRESENT_NOT_ATTESTED"}
    except Exception as exc:
        return {"status": "INVALID_UNVERIFIED", "reason": type(exc).__name__}


def diagnostic(c, session):
    require(date.fromisoformat(session).isoformat() == session,
            "INVALID_SESSION")
    require(c["sts"].get_caller_identity().get("Account") == ACCOUNT,
            "WRONG_ACCOUNT_STOP_ALL")
    cf, ev = c["cloudformation"], c["events"]
    st, prod = outputs(cf, ST), outputs(cf, PROD)
    require(st.get("CandidateDataBucket") == BUCKET and
            prod.get("CandidateDataBucket") == PROD_BUCKET,
            "WRONG_BUCKET_ISOLATION")
    problems = []
    schedules = {}
    for stack_name, stack, crons in (
        (ST, st, EXPECTED_ST_CRON),
        (PROD, prod, EXPECTED_PROD_CRON),
    ):
        for key, expected_cron in zip(RULE_KEYS, crons):
            require(key in stack, "MISSING_STACK_OUTPUT:" + key)
            actual = ev.describe_rule(Name=stack[key])
            state = actual.get("State")
            cron = actual.get("ScheduleExpression")
            schedules[stack_name + "/" + key] = {"state": state,
                                                    "cron_match": cron == expected_cron}
            if cron != expected_cron:
                problems.append("SCHEDULE_DRIFT:" + stack_name + "/" + key)
            if stack_name == PROD and state != "DISABLED":
                problems.append("PROD_RULE_NOT_DISABLED:" + key)
            if stack_name == ST:
                if key == RULE_KEYS[0] and state != "ENABLED":
                    problems.append("ST_SIGNAL_RULE_NOT_ENABLED")
                if key == RULE_KEYS[1] and state != "ENABLED":
                    problems.append("ST_PAPER_RULE_NOT_ENABLED")
                if key == RULE_KEYS[2] and state != "DISABLED":
                    problems.append("ST_ORCHESTRATOR_RULE_NOT_DISABLED")
    alarms = []
    token = None
    for _ in range(10):
        opts = {"AlarmNamePrefix": ALARM_PREFIX, "MaxRecords": 100}
        if token: opts["NextToken"] = token
        result = c["cloudwatch"].describe_alarms(**opts)
        alarms.extend({"name": a.get("AlarmName"), "state": a.get("StateValue")}
                      for a in result.get("MetricAlarms", []))
        token = result.get("NextToken")
        if not token:
            break
    else:
        problems.append("ALARM_INVENTORY_INCOMPLETE")
    if not alarms:
        problems.append("NO_ST_ALARMS")
    bad_alarms = [a for a in alarms if a["state"] != "OK"]
    if bad_alarms:
        problems.append("ST_ALARMS_NON_OK:" + str(len(bad_alarms)))
    versioning = c["s3"].get_bucket_versioning(Bucket=BUCKET).get("Status")
    if versioning != "Enabled":
        problems.append("ST_BUCKET_VERSIONING_NOT_ENABLED")
    objects = {
        "signal": object_status(c["s3"], f"signals/{session}.json"),
        "paper": object_status(c["s3"], f"paper/sessions/{session}.json"),
        "continuity": object_status(c["s3"], f"paper/continuity/{session}.json"),
    }
    for name, state in objects.items():
        if state["status"] != "VERSIONED_JSON_PRESENT_NOT_ATTESTED":
            problems.append("ST_" + name.upper() + "_" + state["status"])
    return {
        "status": ("BLOCKED_WITH_INDEPENDENT_OBSERVATIONS" if problems else
                   "NO_OBVIOUS_BLOCKERS_NOT_PAPER_ACCEPTANCE"),
        "session": session,
        "checked_utc": datetime.now(timezone.utc).isoformat(),
        "schedules": schedules, "alarms_non_ok": bad_alarms,
        "s3_objects": objects, "blockers": problems,
        "no_paper_chain_attestation_performed": True,
        "historic_missing_sessions_not_backfilled": True,
        "aws_mutations": False, "lambda_invocations": False,
        "prod_mutations": False, "broker_orders": False,
    }


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--session", required=True)
    args = p.parse_args(argv)
    try:
        import boto3
        s = boto3.Session(region_name=REGION)
        clients = {n: s.client(n) for n in
                   ("sts", "cloudformation", "events", "s3", "cloudwatch")}
        result = diagnostic(clients, args.session)
    except Exception as exc:
        result = {"status": "DIAGNOSTIC_UNVERIFIED",
                  "reason": str(exc)[:240], "aws_mutations": False,
                  "lambda_invocations": False, "broker_orders": False}
    print(json.dumps(result, sort_keys=True, indent=2))
    # The diagnostic is informational and cannot override the subsequent
    # strict acceptance. An inability to read resources is itself an error.
    return 2 if result["status"] == "DIAGNOSTIC_UNVERIFIED" else 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fail-closed ST-only containment for a VERIFIED duplicate legacy Signal schedule.

Read-only by default. Optional operator-approved pause disables ONLY the
stocklens-independent-staging Signal EventBridge rule, after verifying the
primary ST signal, both real CloudWatch vendor-lag incidents, exact rule
targets and all PROD rules disabled. It does not fix Paper continuity, alter
alarms or authorize trading. Does not deploy a newer Signal runtime.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import sys

ACCOUNT = "634740393398"
REGION = "eu-central-1"
ST = "stocklens-st"
LEGACY = "stocklens-independent-staging"
PROD = "stocklens-prod"
ST_BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
PROD_BUCKET = "stocklens-prod-candidatedata-c3yge4ymwb7u"
ST_SIGNAL = "stocklens-st-candidate"
LEGACY_SIGNAL = "stocklens-independent-staging-candidate"
PROOF_SESSION = "2026-11-17"
# This evidence is only sufficient until the next XNYS open; never use stale proof.
PROOF_EXPIRES_UTC = datetime(2026, 11, 19, 14, 30, tzinfo=timezone.utc)
ST_SIGNAL_CRON = "cron(30 5,8,11,12 ? * TUE-SAT *)"
OLD_SIGNAL_CRON = "cron(30 2 ? * TUE-SAT *)"
RULE_KEYS = ("CandidateSignalOnlyRuleName", "CandidatePaperOnlyRuleName",
             "CandidateOrchestratorRuleName")
ERROR_PROOFS = (
    ("2026-11-17T02:00:00+00:00", "2026-11-17T03:00:00+00:00",
     "CANONICAL_INGEST_STALE_LAST_SESSION:expected=2026-11-16:vendor_last=2026-11-13:audit_last=2026-11-13"),
    ("2026-11-18T02:00:00+00:00", "2026-11-18T03:00:00+00:00",
     "CANONICAL_INGEST_STALE_LAST_SESSION:expected=2026-11-17:vendor_last=2026-11-16:audit_last=2026-11-16"),
)


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def outputs(cf, name):
    res = cf.describe_stacks(StackName=name)["Stacks"]
    require(len(res) == 1 and res[0]["StackStatus"] in
            ("CREATE_COMPLETE", "UPDATE_COMPLETE"), "UNSTABLE_STACK:" + name)
    return {v["OutputKey"]: v["OutputValue"] for v in res[0].get("Outputs", [])}


def rule(ev, name, *, cron, state, function_arn=None):
    obj = ev.describe_rule(Name=name)
    require(obj.get("State") == state and obj.get("ScheduleExpression") == cron,
            "RULE_STATE_OR_CRON_DRIFT:" + name)
    if function_arn is not None:
        targets = ev.list_targets_by_rule(Rule=name).get("Targets", [])
        require(len(targets) == 1 and targets[0].get("Arn") == function_arn,
                "EVENT_TARGET_DRIFT:" + name)
    return obj


def lambda_config(lam, name, bucket):
    cfg = lam.get_function_configuration(FunctionName=name)
    require(cfg.get("State") == "Active" and
            cfg.get("LastUpdateStatus") == "Successful" and
            cfg.get("Handler") == "infra.aws.independent_pipeline.handler" and
            isinstance(cfg.get("CodeSha256"), str) and len(cfg["CodeSha256"]) > 20 and
            cfg.get("Environment", {}).get("Variables", {}).get("STOCKLENS_DATA_BUCKET") == bucket,
            "UNVERIFIED_LAMBDA_CONFIGURATION:" + name)
    return cfg


def verify_st_signal(s3):
    require(s3.get_bucket_versioning(Bucket=ST_BUCKET).get("Status") == "Enabled",
            "ST_BUCKET_VERSIONING_OFF")
    key = "signals/" + PROOF_SESSION + ".json"
    o = s3.get_object(Bucket=ST_BUCKET, Key=key)
    v = o.get("VersionId")
    require(isinstance(v, str) and v not in ("", "null") and
            type(o.get("ContentLength")) is int and 2 <= o["ContentLength"] <= 2_000_000,
            "ST_SOURCE_VERSION_OR_SIZE_INVALID")
    body = o["Body"].read(2_000_001)
    require(len(body) == o["ContentLength"], "ST_SIGNAL_LENGTH_MISMATCH")
    doc = json.loads(body)
    require(doc.get("mode") == "SHADOW_ONLY_NO_BROKER_ACTIONS" and
            doc.get("latest", {}).get("asof_date") == PROOF_SESSION and
            doc.get("execution_plan", {}).get("broker_actions_enabled") is False,
            "ST_SIGNAL_NOT_QUALIFIED_OR_BROKER_UNSAFE")
    return {"session": PROOF_SESSION, "sha256": hashlib.sha256(body).hexdigest(),
            "s3_versioned": True, "broker_actions": False}


def prove_errors(logs):
    group = "/aws/lambda/" + LEGACY_SIGNAL
    for start, stop, needle in ERROR_PROOFS:
        args = {"logGroupName": group,
                "startTime": int(datetime.fromisoformat(start).timestamp() * 1000),
                "endTime": int(datetime.fromisoformat(stop).timestamp() * 1000),
                "limit": 1000}
        found = False
        token = None
        for _ in range(4):
            q = dict(args)
            if token:
                q["nextToken"] = token
            result = logs.filter_log_events(**q)
            found |= any(needle in e.get("message", "") for e in result.get("events", []))
            if found:
                break
            nxt = result.get("nextToken")
            if not nxt or nxt == token:
                break
            token = nxt
        require(found, "OLD_LEGACY_VENDOR_LAG_LOG_NOT_PROVEN:" + start[:10])
    return {"two_historical_incidents_verified": True,
            "source": "AWS_CLOUDWATCH_LOGS_NOT_REPLAYED"}


def preflight(c, *, now=None):
    now = now or datetime.now(timezone.utc)
    require(now.tzinfo is not None and now.astimezone(timezone.utc) < PROOF_EXPIRES_UTC,
            "LEGACY_CONTAINMENT_EVIDENCE_EXPIRED")
    require(c["sts"].get_caller_identity().get("Account") == ACCOUNT, "WRONG_ACCOUNT")
    cf, ev, lam = c["cloudformation"], c["events"], c["lambda"]
    st, old, prod = (outputs(cf, name) for name in (ST, LEGACY, PROD))
    require(st.get("CandidateDataBucket") == ST_BUCKET and
            prod.get("CandidateDataBucket") == PROD_BUCKET and
            old.get("CandidateFunctionName") == LEGACY_SIGNAL and
            st.get("CandidateFunctionName") == ST_SIGNAL,
            "STACK_ISOLATION_OR_OUTPUTS_UNVERIFIED")
    for name in RULE_KEYS:
        require(name in st and name in old and name in prod,
                "MISSING_SCHEDULE_OUTPUT:" + name)
        prod_rule = ev.describe_rule(Name=prod[name])
        require(prod_rule.get("State") == "DISABLED",
                "PROD_SCHEDULE_MUST_REMAIN_DISABLED:" + name)
    st_cfg = lambda_config(lam, ST_SIGNAL, ST_BUCKET)
    old_cfg = lambda_config(lam, LEGACY_SIGNAL, old["CandidateDataBucket"])
    rule(ev, st["CandidateSignalOnlyRuleName"], cron=ST_SIGNAL_CRON,
         state="ENABLED", function_arn=st_cfg["FunctionArn"])
    legacy_rule = old["CandidateSignalOnlyRuleName"]
    rule(ev, legacy_rule, cron=OLD_SIGNAL_CRON,
         state="ENABLED", function_arn=old_cfg["FunctionArn"])
    proof = verify_st_signal(c["s3"])
    incidents = prove_errors(c["logs"])
    return {
        "status": "ST_ONLY_LEGACY_SIGNAL_PAUSE_ELIGIBLE_NOT_EXECUTED",
        "legacy_rule": legacy_rule, "legacy_lambda": LEGACY_SIGNAL,
        "st_verified_signal": proof, "legacy_error_evidence": incidents,
        "prod_all_schedules_disabled": True,
        "st_primary_signal_schedule_enabled": True,
        "old_paper_continuity_recovered": False,
        "alarm_history_preserved": True,
        "broker_orders": False,
    }


def run(c, mode, approved=False, *, now=None):
    require(mode in ("inspect", "pause"), "UNKNOWN_MODE")
    require((mode == "pause") == approved, "EXPLICIT_OPERATOR_APPROVAL_REQUIRED")
    check = preflight(c, now=now)
    check["mode"] = mode
    if mode == "inspect":
        check["aws_mutations"] = False
        return check
    fresh = preflight(c, now=now)
    require(fresh["legacy_rule"] == check["legacy_rule"] and
            fresh["st_verified_signal"]["sha256"] == check["st_verified_signal"]["sha256"],
            "CONCURRENT_EVIDENCE_CHANGE_REVIEW_REQUIRED")
    c["events"].disable_rule(Name=check["legacy_rule"])
    verify = c["events"].describe_rule(Name=check["legacy_rule"])
    require(verify.get("State") == "DISABLED",
            "LEGACY_STAGING_SIGNAL_PAUSE_NOT_CONFIRMED")
    return {
        "status": "LEGACY_STAGING_SIGNAL_SCHEDULE_PAUSED_NOT_PAPER_RECOVERY",
        "disabled_rule": check["legacy_rule"],
        "prod_untouched": True, "st_primary_schedule_untouched": True,
        "paper_and_watchdog_untouched": True, "alarms_untouched": True,
        "cloudformation_drift_requires_reconciliation": True,
        "broker_orders": False, "aws_mutations": True,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("inspect", "pause"))
    parser.add_argument("--approve-staging-legacy-signal-pause", action="store_true")
    args = parser.parse_args(argv)
    try:
        import boto3
        s = boto3.Session(region_name=REGION)
        c = {k: s.client(k) for k in
             ("sts", "cloudformation", "events", "lambda", "s3", "logs")}
        result = run(c, args.mode, args.approve_staging_legacy_signal_pause)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED_OR_PARTIAL_REVIEW_REQUIRED",
                          "reason": str(exc)[:230],
                          "broker_orders": False,
                          "prod_change_requested": False}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Fallback ST-only weekend Lambda code release when CFN change set is unsafe.

READ: never execute the existing 15-resource CFN change set: it contains IAM,
Lambda permissions and EventBridge rule changes, not five Lambda Code changes.

inspect   : authenticated read-only report.
deploy --yes --acknowledge-cfn-drift:
  1. Requires Saturday 08:00 UTC through Sunday 22:00 UTC (no scheduled US
     market Signal/Paper sessions in this project's Tue-Sat UTC cron).
  2. Re-verifies exact Lambda revisions, current ST-only schedule targets,
     verified immutable local ZIP and staged source artifact.
  3. Places a new content-addressed object in VERSIONED ST-only S3.
  4. Calls Lambda UpdateFunctionCode DryRun for all five ST functions.
  5. Removes ONLY the explicitly identified UNEXECUTED, unsafe ST CFN change set.
  6. Uses UpdateFunctionCode with RevisionId + S3ObjectVersion, no permissions,
     config, environment, EventBridge, CFN stack or PROD changes.
  7. Verifies five SHA256, original non-code configs and exact schedules; records
     CloudFormation CODE DRIFT requiring a later, separately reviewed reconciliation.

A partial deployment stops, never silently replays Paper or fakes receipts.
Lambda code updates are real AWS mutations ONLY when deploy flags are passed.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sys
import time

from infra.aws import st_paper_cfn_guarded_release as g
from infra.aws import st_paper_prepare_review_zip as p

ACCOUNT = p.ACCOUNT
REGION = p.REGION
ST = p.ST
PROD = p.PROD
OLD = g.OLD_SHA_B64
NEW = g.LOCAL_CANDIDATE_SHA_B64
RULE_KEYS = p.RULES
ORIGINAL_CF_CHANGESET_NAME = g.CHANGE_NAME
RESOURCE_IDS = {
    "CandidateLambda",
    "CandidateOrchestratorLambda",
    "CandidateOrchestratorRole",
    "CandidateOrchestratorSchedulePermission",
    "CandidateOrchestratorSchedule",
    "CandidatePaperLambda",
    "CandidatePaperOnlySchedulePermission",
    "CandidatePaperOnlySchedule",
    "CandidatePaperPreflightLambda",
    "CandidateSessionWatchdogLambda",
    "CandidateSessionWatchdogPermission",
    "CandidateSessionWatchdogRole",
    "CandidateSessionWatchdogSchedule",
    "CandidateSignalOnlySchedulePermission",
    "CandidateSignalOnlySchedule",
}
EXPECTED_EVENTS = {
    "CandidateSignalOnlyRuleName": "CandidateFunctionName",
    "CandidatePaperOnlyRuleName": "CandidatePaperFunctionName",
    "CandidateOrchestratorRuleName": "CandidateOrchestratorFunctionName",
}
CONFIG_KEYS = (
    "FunctionArn", "FunctionName", "Role", "Runtime", "Handler", "PackageType",
    "Timeout", "MemorySize", "EphemeralStorage", "Architectures",
    "Environment", "VpcConfig", "Layers", "FileSystemConfigs",
    "DeadLetterConfig", "TracingConfig", "KMSKeyArn", "LoggingConfig",
)
ORDER = (
    "CandidateFunctionName",
    "CandidateOrchestratorFunctionName",
    "CandidateSessionWatchdogFunctionName",
    "CandidatePaperPreflightFunctionName",
    "CandidatePaperFunctionName",
)


def require(x, msg):
    if not x:
        raise RuntimeError(msg)


def window_ok(now: datetime):
    now = now.astimezone(timezone.utc)
    if now.weekday() == 5:  # Saturday UTC, only well after Sat 03:20 cron
        return now.hour >= 8
    if now.weekday() == 6:  # Sunday UTC
        return now.hour < 22
    return False


def config_fingerprint(cfg):
    # Privacy-preserving compare: keep config in memory, never print values.
    return {key: cfg.get(key) for key in CONFIG_KEYS}


def read_config(c, function):
    cfg = c["lambda"].get_function_configuration(FunctionName=function)
    require(cfg.get("FunctionName") == function and
            cfg.get("State") == "Active" and
            cfg.get("LastUpdateStatus") == "Successful",
            "ST_LAMBDA_NOT_READY:" + function)
    require(cfg.get("PackageType", "Zip") == "Zip" and
            cfg.get("Version", "$LATEST") == "$LATEST",
            "ST_LAMBDA_NOT_MUTABLE_ZIP:" + function)
    require(bool(cfg.get("RevisionId")) and bool(cfg.get("FunctionArn")),
            "ST_LAMBDA_UNVERSIONED_OR_UNIDENTIFIED:" + function)
    require(cfg.get("FunctionArn", "").startswith(
            "arn:aws:lambda:" + REGION + ":" + ACCOUNT + ":function:" + ST + "-"),
            "ST_LAMBDA_WRONG_FUNCTION_ARN")
    return cfg


def verify_event_targets(c, state, config):
    st = state["st_outputs"]
    ev = c["events"]
    target_proof = {}
    for rule_key, fn_key in EXPECTED_EVENTS.items():
        rule = st[rule_key]
        function = st[fn_key]
        targets = ev.list_targets_by_rule(Rule=rule).get("Targets", [])
        require(len(targets) == 1 and
                targets[0].get("Arn") == config[function]["FunctionArn"],
                "ST_SCHEDULE_TARGET_DIFFERS_FROM_LAMBDA:" + rule_key)
        target_proof[rule_key] = True
    # Watchdog is hourly and has a resource-bound EventBridge target.
    watchdog_res = c["cloudformation"].describe_stack_resource(
        StackName=ST, LogicalResourceId="CandidateSessionWatchdogSchedule")
    rule_name = watchdog_res["StackResourceDetail"]["PhysicalResourceId"]
    watchdog_fn = st["CandidateSessionWatchdogFunctionName"]
    targets = ev.list_targets_by_rule(Rule=rule_name).get("Targets", [])
    require(len(targets) == 1 and
            targets[0].get("Arn") == config[watchdog_fn]["FunctionArn"],
            "ST_WATCHDOG_TARGET_WRONG")
    target_proof["CandidateSessionWatchdogSchedule"] = True
    return target_proof


def trusted_inventory(c):
    state = g.safe_state(c)
    st = state["st_outputs"]
    config = {}
    for key in ORDER:
        fn = st[key]
        config[fn] = read_config(c, fn)
    require(len(config) == 5, "NOT_FIVE_ST_LAMBDAS")
    require({config[fn]["CodeSha256"] for fn in config} <= {OLD, NEW},
            "UNRECOGNIZED_LAMBDA_CODE")
    schedule = verify_event_targets(c, state, config)
    return state, config, schedule


def unsafe_changeset_summary(c):
    """Only this exact 15-resource ST change set may be retired on deploy."""
    cf = c["cloudformation"]
    result = cf.describe_change_set(
        StackName=ST, ChangeSetName=ORIGINAL_CF_CHANGESET_NAME)
    require(result.get("StackName") == ST and
            result.get("ChangeSetName") == ORIGINAL_CF_CHANGESET_NAME and
            result.get("Status") == "CREATE_COMPLETE" and
            result.get("ExecutionStatus") == "AVAILABLE" and
            not result.get("NextToken"), "ORIGINAL_CHANGESET_UNEXPECTED_OR_PAGED")
    changes = result.get("Changes", [])
    keys = [x.get("ResourceChange", {}).get("LogicalResourceId") for x in changes]
    require(len(keys) == 15 and set(keys) == RESOURCE_IDS and
            all(x.get("ResourceChange", {}).get("Action") == "Modify" for x in changes),
            "ORIGINAL_CHANGESET_CHANGED_REVIEW_BEFORE_RETIRE")
    return {"name": ORIGINAL_CF_CHANGESET_NAME,
            "status": "AVAILABLE_NOT_EXECUTED",
            "unsafe_resource_count": len(keys)}


def artifact_key():
    raw = base64.b64decode(NEW)
    return "release-artifacts/st-paper-engine-sha256-" + raw.hex() + ".zip"


def ensure_versioned_st_artifact(c, package):
    """May write exactly one new object to ST's already versioned private bucket."""
    s3 = c["s3"]
    require(s3.get_bucket_versioning(Bucket=p.ST_BUCKET).get("Status") == "Enabled",
            "ST_BUCKET_NOT_VERSIONED")
    key = artifact_key()
    try:
        meta = s3.head_object(Bucket=p.ST_BUCKET, Key=key)
        require(meta.get("Metadata", {}).get("stocklens-sha256-b64") == NEW,
                "EXISTING_ARTIFACT_METADATA_WRONG")
    except Exception as exc:
        code = (getattr(exc, "response", {}) or {}).get("Error", {}).get("Code")
        require(str(code) in ("404", "NoSuchKey", "NotFound"),
                "UNVERIFIED_ST_ARTIFACT_S3_READ_ERROR")
        s3.put_object(Bucket=p.ST_BUCKET, Key=key, Body=package, IfNoneMatch="*",
                      Metadata={"stocklens-sha256-b64": NEW})
    meta = s3.head_object(Bucket=p.ST_BUCKET, Key=key)
    version = meta.get("VersionId")
    require(isinstance(version, str) and version not in ("", "null"),
            "ST_ARTIFACT_NO_S3_VERSION_ID")
    blob = s3.get_object(Bucket=p.ST_BUCKET, Key=key, VersionId=version)["Body"].read(
        p.ZIP_SIZE_LIMIT + 1)
    require(g.digest(blob) == NEW, "ST_ARTIFACT_VERSION_BYTES_UNVERIFIED")
    return {"bucket": p.ST_BUCKET, "key": key, "version": version}


def check_readonly(c):
    state, configs, schedule = trusted_inventory(c)
    live = {key: config["CodeSha256"] for key, config in configs.items()}
    # Once the five audited ST code updates finish, the unsafe CFN change set
    # has been retired deliberately. Post-deploy inspect must recognize only
    # this precisely defined success state, never conceal a missing change set
    # before a release or during a partially updated Lambda fleet.
    try:
        change = unsafe_changeset_summary(c)
    except Exception as exc:
        response = getattr(exc, "response", {}) or {}
        code = str(response.get("Error", {}).get("Code", ""))
        msg = str(response.get("Error", {}).get("Message", ""))
        not_found = code == "ChangeSetNotFound" or (
            code == "ValidationError" and
            ("does not exist" in msg.lower() or "not found" in msg.lower())
        )
        require(not_found and set(live.values()) == {NEW},
                "DANGEROUS_CHANGE_SET_UNVERIFIED_OR_MISSING_BEFORE_COMPLETE_DEPLOY")
        change = {"name": ORIGINAL_CF_CHANGESET_NAME,
                  "status": "RETIRED_NOT_EXECUTED",
                  "unsafe_resource_count": 0}
    return {
        "status": "ST_DIRECT_CODE_RELEASE_READ_ONLY",
        "current_lambdas": len(configs),
        "current_all_original": set(live.values()) == {OLD},
        "current_all_candidate": set(live.values()) == {NEW},
        "mixed_or_partial_code": len(set(live.values())) > 1,
        "private_candidate_sha256_b64": NEW,
        "prepared_local_candidate_sha256_verified": (
            g.digest(g.candidate_bytes()) == NEW),
        "st_rule_targets_verified": schedule,
        "st_orchestrator_schedule": "DISABLED",
        "prod_schedules_all_disabled": state["prod_schedules_all_disabled"],
        "blocked_cfn_change_set": change,
        "cloudformation_template_still_points_old_code": True,
        "cfn_drift_if_direct_update": True,
        "deploy_permitted_window_now": window_ok(datetime.now(timezone.utc)),
        "aws_mutations": False,
        "broker_orders": False,
        "paper_backfill": False,
    }


def apply_direct(c, *, approved=False, acknowledged=False,
                 now=None, sleep=time.sleep):
    require(approved and acknowledged,
            "EXPLICIT_--yes_AND_--acknowledge-cfn-drift_REQUIRED")
    now = now or datetime.now(timezone.utc)
    require(window_ok(now), "WEEKEND_MAINTENANCE_WINDOW_ONLY")
    state, before, schedule = trusted_inventory(c)
    require(all(cfg.get("CodeSha256") == OLD for cfg in before.values()),
            "ST_MIXED_OR_NEW_CODE_REQUIRES_MANUAL_RECOVERY")
    unsafe_changeset_summary(c)
    # Two separate proofs for same private local file & staged CF source artifact.
    pkg = g.candidate_bytes()
    require(g.digest(pkg) == NEW, "LOCAL_CANDIDATE_SHA_CHANGED")
    g.verify_staged_artifact(c, state)
    # S3 artifact object is versioned; Lambda UpdateFunctionCode pins that exact
    # VersionId and each function's exact RevisionId to prevent races.
    artifact = ensure_versioned_st_artifact(c, pkg)
    lam = c["lambda"]
    for fn in before:
        lam.update_function_code(
            FunctionName=fn, S3Bucket=artifact["bucket"],
            S3Key=artifact["key"], S3ObjectVersion=artifact["version"],
            RevisionId=before[fn]["RevisionId"], Publish=False, DryRun=True)
    # The old CFN change set is known unsafe. Delete only this exact, checked
    # change set (never the stack), so it cannot later undo schedule safety.
    c["cloudformation"].delete_change_set(
        StackName=ST, ChangeSetName=ORIGINAL_CF_CHANGESET_NAME)
    print("ST_ONLY_UNSAFE_CHANGE_SET_RETIRED", flush=True)
    results = []
    for key in ORDER:
        fn = state["st_outputs"][key]
        last = read_config(c, fn)
        require(last["RevisionId"] == before[fn]["RevisionId"] and
                last["CodeSha256"] == OLD and
                config_fingerprint(last) == config_fingerprint(before[fn]),
                "FUNCTION_CHANGED_DURING_APPROVAL:" + key)
        lam.update_function_code(
            FunctionName=fn, S3Bucket=artifact["bucket"],
            S3Key=artifact["key"], S3ObjectVersion=artifact["version"],
            RevisionId=last["RevisionId"], Publish=False)
        for attempt in range(80):
            seen = lam.get_function_configuration(FunctionName=fn)
            if seen.get("LastUpdateStatus") == "Successful" and seen.get("State") == "Active":
                break
            if seen.get("LastUpdateStatus") == "Failed":
                raise RuntimeError("PARTIAL_DEPLOY_LAMBDA_UPDATE_FAILED:" + key)
            sleep(2)
        else:
            raise RuntimeError("PARTIAL_DEPLOY_LAMBDA_UPDATE_TIMEOUT:" + key)
        require(seen.get("CodeSha256") == NEW and
                config_fingerprint(seen) == config_fingerprint(before[fn]),
                "PARTIAL_DEPLOY_SHA_OR_CONFIGURATION_DRIFT:" + key)
        results.append(key)
        print("ST_ONLY_LAMBDA_CODE_SHA_VERIFIED:" + key, flush=True)
    final_state, after, final_rules = trusted_inventory(c)
    require(all(cfg["CodeSha256"] == NEW for cfg in after.values()),
            "POST_DEPLOY_FIVE_LAMBDA_CODE_PARITY_FAILED")
    require(final_rules == schedule and
            final_state["prod_schedules_all_disabled"],
            "POST_DEPLOY_ST_OR_PROD_SCHEDULE_DRIFT")
    require(all(config_fingerprint(after[fn]) == config_fingerprint(before[fn])
                for fn in before), "POST_DEPLOY_NONCODE_CONFIGURATION_DRIFT")
    return {
        "status": "ST_ONLY_FIVE_LAMBDA_CODES_DEPLOYED_AND_VERIFIED",
        "patched_sha256_b64": NEW,
        "lambda_updates": results,
        "st_schedule_targets_unchanged": True,
        "prod_schedules_all_disabled": True,
        "cfn_template_code_source_drift": "KNOWN_AND_REQUIRES_FUTURE_RECONCILIATION",
        "old_15_resource_change_set": "DELETED_NOT_EXECUTED",
        "paper_2026_11_05": "MISSING_NEVER_REPLAYED",
        "prospective_paper_receipts": "UNVERIFIED",
        "broker_orders": False,
        "paper_backfill": False,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("inspect", "deploy"))
    parser.add_argument("--yes", action="store_true")
    parser.add_argument("--acknowledge-cfn-drift", action="store_true")
    args = parser.parse_args()
    require(args.mode == "deploy" or not (
        args.yes or args.acknowledge_cfn_drift),
        "APPROVAL_FLAGS_ONLY_ALLOWED_FOR_DEPLOY")
    import boto3
    c = g.sdk_clients(boto3)
    if args.mode == "inspect":
        response = check_readonly(c)
    else:
        response = apply_direct(c, approved=args.yes,
                                acknowledged=args.acknowledge_cfn_drift)
    print(json.dumps(response, sort_keys=True, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED_OR_PARTIAL_DEPLOY_REVIEW_REQUIRED",
                          "reason": str(exc)[:250],
                          "no_prod_changes_by_this_script": True,
                          "broker_orders": False, "paper_backfill": False}))
        raise SystemExit(2)

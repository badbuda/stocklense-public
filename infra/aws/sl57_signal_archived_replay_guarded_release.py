#!/usr/bin/env python3
"""SL-57 incident 2026-11-10: ST Signal-only, SHA-pinned repeat-safe patch.

Inspect is read-only. Apply checks all conditions, updates *only*
stocklens-st-candidate Lambda code with the exact reviewed independent_pipeline.py
source, then verifies the function. Never touches PROD, Paper, Watchdog, S3
receipts, EventBridge schedules, broker, or alarm state. Unrelated private
runtime ZIP members are preserved byte-for-byte. Unknown baseline fails closed.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import sys
import urllib.request
import zipfile

ACCOUNT = "634740393398"
REGION = "eu-central-1"
REPO = "badbuda/stocklense-public"
REF = "acc16022081bb6f8ea6714889ec360a18515c978"
PATH = "infra/aws/independent_pipeline.py"
# Actual 2026-11-10 post-deploy release signed by operator, not a guess.
CURRENT_ZIP_SHA256_B64 = "YKpLN8Ks36blX4J9z+GnDKx9fCN87tA7wwc5Sc/25WQ="
OLD_PIPELINE_GIT_BLOB_SHA = "a519d8800d58dc60b65d9e474b51f1153bb00d0c"
NEW_PIPELINE_GIT_BLOB_SHA = "fc458444ad11c89f722eab38b61056a6a5a894f1"
REQUIRED_SIGNAL_CRON = "cron(30 5,8,11,12 ? * TUE-SAT *)"
REQUIRED_PAPER_CRON = "cron(0 13 ? * TUE-SAT *)"
INCIDENT_SESSION = "2026-11-09"


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def blob_sha(raw):
    return hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()


def sha256_b64(raw):
    return base64.b64encode(hashlib.sha256(raw).digest()).decode()


def pinned_source():
    url = f"https://raw.githubusercontent.com/{REPO}/{REF}/{PATH}"
    with urllib.request.urlopen(urllib.request.Request(
            url, headers={"User-Agent": "stocklens-reviewed-st-signal-patch"}),
            timeout=45) as response:
        raw = response.read(250_001)
    require(len(raw) <= 250_000 and blob_sha(raw) == NEW_PIPELINE_GIT_BLOB_SHA,
            "PINNED_SIGNAL_SOURCE_MISMATCH")
    import ast
    ast.parse(raw.decode("utf-8"), filename=PATH)
    require(b"STAGED_SIGNAL_ALREADY_ARCHIVED_VERIFIED" in raw
            and b"ARCHIVED_SIGNAL_FROZEN_REPLAY_MISMATCH" in raw
            and b"INCOMPLETE_IMMUTABLE_SIGNAL_ARCHIVE" in raw,
            "PINNED_SIGNAL_ARCHIVE_GUARDS_NOT_PRESENT")
    return raw


def patch_zip(original: bytes, source: bytes):
    require(sha256_b64(original) == CURRENT_ZIP_SHA256_B64,
            "DEPLOYED_LAMBDA_ZIP_CHANGED_STOP")
    require(blob_sha(source) == NEW_PIPELINE_GIT_BLOB_SHA,
            "PATCH_CONTENT_NOT_PINNED")
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original), "r") as archive:
        infos = archive.infolist()
        names = [f.filename for f in infos]
        require(len(infos) > 100 and len(names) == len(set(names)),
                "UNEXPECTED_DEPLOYED_ZIP_STRUCTURE")
        require(names.count(PATH) == 1, "DEPLOYED_PIPELINE_MISSING")
        require(blob_sha(archive.read(PATH)) == OLD_PIPELINE_GIT_BLOB_SHA,
                "DEPLOYED_PIPELINE_SOURCE_CHANGED_STOP")
        require("stocklens/st_signal_retry_policy.py" in names,
                "MISSING_PREVIOUS_ST_RETRY_POLICY")
        with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED,
                             compresslevel=6) as candidate:
            for info in infos:
                candidate.writestr(info,
                                   source if info.filename == PATH
                                   else archive.read(info.filename))
    result = out.getvalue()
    require(len(result) < 49_000_000, "LAMBDA_DIRECT_UPDATE_SIZE_LIMIT")
    with zipfile.ZipFile(io.BytesIO(result)) as final:
        require(final.namelist() == names, "ZIP_FILE_LIST_CHANGED")
        require(blob_sha(final.read(PATH)) == NEW_PIPELINE_GIT_BLOB_SHA,
                "NEW_PIPELINE_NOT_VERIFIED")
        with zipfile.ZipFile(io.BytesIO(original)) as old:
            for name in names:
                if name != PATH:
                    require(final.read(name) == old.read(name),
                            "UNRELATED_PRIVATE_RUNTIME_MEMBER_CHANGED:" + name)
    return result


def output_map(cf, stack):
    records = cf.describe_stacks(StackName=stack)["Stacks"]
    require(len(records) == 1 and
            records[0]["StackStatus"] in ("CREATE_COMPLETE", "UPDATE_COMPLETE"),
            "STACK_NOT_STABLE:" + stack)
    return {x["OutputKey"]: x["OutputValue"]
            for x in records[0].get("Outputs", [])}


def preflight(session):
    sts = session.client("sts")
    require(sts.get_caller_identity()["Account"] == ACCOUNT, "WRONG_AWS_ACCOUNT")
    cf = session.client("cloudformation")
    events = session.client("events")
    lam = session.client("lambda")
    s3 = session.client("s3")
    st = output_map(cf, "stocklens-st")
    prod = output_map(cf, "stocklens-prod")
    require(st["CandidateDataBucket"] != prod["CandidateDataBucket"],
            "ST_PROD_BUCKET_NOT_ISOLATED")
    require(s3.get_bucket_versioning(
        Bucket=st["CandidateDataBucket"]).get("Status") == "Enabled",
            "ST_DATA_BUCKET_NOT_VERSIONED")
    for key in ("CandidateSignalOnlyRuleName",
                "CandidatePaperOnlyRuleName",
                "CandidateOrchestratorRuleName"):
        st_rule = events.describe_rule(Name=st[key])
        prod_rule = events.describe_rule(Name=prod[key])
        require(prod_rule["State"] == "DISABLED",
                "PROD_RULE_NOT_DISARMED:" + key)
        wanted = ("DISABLED" if key == "CandidateOrchestratorRuleName"
                  else "ENABLED")
        require(st_rule["State"] == wanted,
                "ST_RULE_WRONG_STATE:" + key)
        if key == "CandidateSignalOnlyRuleName":
            require(st_rule["ScheduleExpression"] == REQUIRED_SIGNAL_CRON,
                    "ST_SIGNAL_RETRY_CRON_CHANGED")
        if key == "CandidatePaperOnlyRuleName":
            require(st_rule["ScheduleExpression"] == REQUIRED_PAPER_CRON,
                    "ST_PAPER_CRON_CHANGED")
    fn = st["CandidateFunctionName"]
    require(fn.startswith("stocklens-st-"),
            "FUNCTION_NAME_NOT_ST")
    cfg = lam.get_function_configuration(FunctionName=fn)
    require(cfg["State"] == "Active"
            and cfg["LastUpdateStatus"] == "Successful"
            and cfg["Handler"] == "infra.aws.independent_pipeline.handler"
            and cfg.get("RevisionId"),
            "ST_SIGNAL_FUNCTION_UNREADY")
    require(cfg["CodeSha256"] == CURRENT_ZIP_SHA256_B64,
            "ST_SIGNAL_DEPLOYED_SHA_CHANGED")
    require(cfg.get("Environment", {}).get("Variables", {}).get(
        "STOCKLENS_DATA_BUCKET") == st["CandidateDataBucket"],
            "ST_SIGNAL_BUCKET_MISMATCH")
    targets = events.list_targets_by_rule(
        Rule=st["CandidateSignalOnlyRuleName"]).get("Targets", [])
    require(len(targets) == 1 and targets[0]["Arn"] == cfg["FunctionArn"],
            "ST_SIGNAL_RULE_TARGET_MISMATCH")
    wd = lam.get_function_configuration(
        FunctionName=st["CandidateSessionWatchdogFunctionName"])
    require(wd.get("Environment", {}).get("Variables", {}).get(
        "SIGNAL_V2_START_SESSION") == "2026-11-10",
            "ST_V2_MONITORING_CHANGED")
    # Only version/head metadata: no body values or private data printed.
    for key in (f"market/qqq/{INCIDENT_SESSION}.csv",
                f"manifests/qqq/{INCIDENT_SESSION}.json",
                f"signals/{INCIDENT_SESSION}.json"):
        obj = s3.head_object(Bucket=st["CandidateDataBucket"], Key=key)
        require(obj.get("VersionId") not in (None, "null", ""),
                "INCIDENT_SOURCE_UNVERSIONED:" + key)
    response = lam.get_function(FunctionName=fn)
    require(response["Configuration"]["CodeSha256"] == cfg["CodeSha256"],
            "SIGNAL_CODE_CHANGED_MID_INSPECTION")
    with urllib.request.urlopen(response["Code"]["Location"], timeout=90) as file:
        deployed_zip = file.read(60_000_001)
    require(len(deployed_zip) < 60_000_000, "DEPLOYED_ZIP_TOO_BIG")
    return lam, fn, cfg, deployed_zip, st


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("inspect", "apply"))
    parser.add_argument("--approve-st-signal-only", action="store_true")
    args = parser.parse_args()
    if args.mode == "apply":
        require(args.approve_st_signal_only, "APPLY_REQUIRES_EXPLICIT_ST_APPROVAL")
    import boto3
    session = boto3.Session(region_name=REGION)
    lam, fn, cfg, oldzip, st = preflight(session)
    raw = pinned_source()
    newzip = patch_zip(oldzip, raw)
    target_sha = sha256_b64(newzip)
    print(json.dumps({
        "status": "ST_SIGNAL_REPLAY_PATCH_PREFLIGHT_PASS",
        "mode": args.mode, "current_sha": cfg["CodeSha256"],
        "target_sha": target_sha, "source_ref": REF,
        "incident_session": INCIDENT_SESSION, "prod_disarmed": True,
        "s3_archives_preserved": True, "paper_untouched": True,
        "watchdog_untouched": True, "no_broker": True
    }, sort_keys=True), flush=True)
    if args.mode == "inspect":
        return
    result = lam.update_function_code(
        FunctionName=fn, ZipFile=newzip,
        RevisionId=cfg["RevisionId"], Publish=False)
    require(result["CodeSha256"] == target_sha,
            "ST_CODE_UPDATE_SHA_MISMATCH")
    lam.get_waiter("function_updated_v2").wait(
        FunctionName=fn, WaiterConfig={"Delay":5,"MaxAttempts":45})
    done = lam.get_function_configuration(FunctionName=fn)
    require(done["State"] == "Active"
            and done["LastUpdateStatus"] == "Successful"
            and done["CodeSha256"] == target_sha,
            "ST_SIGNAL_CODE_UPDATE_UNVERIFIED")
    print(json.dumps({
        "status": "ST_SIGNAL_VERIFIED_REPLAY_PATCH_DEPLOYED",
        "lambda_function": fn,
        "new_code_sha256_b64": target_sha,
        "paper_watchdog_prod_untouched": True,
        "next_step": "VERIFY_SCHEDULED_RETRY_AND_ARCHIVE_REPLAY_RESULT",
    }, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({
            "status": "ST_SIGNAL_PATCH_BLOCKED_OR_PARTIAL_REVIEW_REQUIRED",
            "reason": str(exc)[:260],
            "no_prod_mutations": True,
        }, sort_keys=True), file=sys.stderr)
        sys.exit(2)

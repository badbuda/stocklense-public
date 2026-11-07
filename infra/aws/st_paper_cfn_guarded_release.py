#!/usr/bin/env python3
"""Reviewed ST-only CloudFormation ZIP promotion; NO brokerage or Paper replay.

inspect: strictly read-only AWS checks.
prepare: upload one new immutable S3 artifact and CREATE an ST-only change set;
         never execute the change set or change any running Lambda.
apply --yes: recheck an already reviewed exact change set; execute only if
         the ONLY changes are expected Code changes to exactly five ST Lambdas.
No EventBridge changes are permitted. The existing CFN signal-schedule parameter
drift intentionally remains, rather than silently changing live schedules.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import sys
import time

from infra.aws import st_paper_prepare_review_zip as preview

REGION = preview.REGION
ACCOUNT = preview.ACCOUNT
ST = preview.ST
PROD = preview.PROD
LOCAL_CANDIDATE_SHA_B64 = "ih8VTt/owwOznYsYCf0/n9kpqqe1MYieNmXpEM0xozY="
OLD_SHA_B64 = "D6RdBiq0PKzcPB9aT2MmnxDo/8dFxuqen0AD4opQV0k="
LAMBDA_OUTPUT_KEYS = (
    "CandidateFunctionName", "CandidatePaperFunctionName",
    "CandidateOrchestratorFunctionName", "CandidatePaperPreflightFunctionName",
    "CandidateSessionWatchdogFunctionName",
)
CHANGE_NAME = "stocklens-st-paper-engine-" + hashlib.sha256(
    base64.b64decode(LOCAL_CANDIDATE_SHA_B64)
).hexdigest()[:14]


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(data):
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def package_path():
    sha = base64.b64decode(LOCAL_CANDIDATE_SHA_B64).hex()
    return Path.home() / ".stocklens-private-st-releases" / ("st-paper-" + sha[:20] + ".zip")


def candidate_bytes():
    path = package_path()
    require(path.is_file(), "LOCAL_PRIVATE_CANDIDATE_ZIP_MISSING")
    require(path.stat().st_size <= preview.ZIP_SIZE_LIMIT, "LOCAL_ZIP_OVERSIZE")
    data = path.read_bytes()
    require(digest(data) == LOCAL_CANDIDATE_SHA_B64, "LOCAL_ZIP_SHA256_CHANGED")
    # Revalidate the only two sensitive source members; never log content.
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        require(len(z.namelist()) == 4381 and len(z.namelist()) == len(set(z.namelist())),
                "UNEXPECTED_ZIP_MEMBER_COUNT_OR_DUPLICATES")
        require(preview.git_blob_sha(z.read(preview.PAPER_PATH)) == preview.NEW_ENGINE_BLOB,
                "FIXED_ENGINE_SOURCE_BLOB_CHANGED")
        require(preview.git_blob_sha(z.read(preview.ENTRY_PATH)) == preview.ENTRY_BLOB,
                "PRIVATE_HANDLER_SOURCE_BLOB_CHANGED")
    return data


def sdk_clients(boto3):
    session = boto3.session.Session(region_name=REGION)
    return {x: session.client(x) for x in
            ("sts", "cloudformation", "lambda", "events", "s3")}


def safe_state(c):
    """Fail closed for all known ST/PROD resource, code and schedule drift."""
    require(c["sts"].get_caller_identity().get("Account") == ACCOUNT,
            "WRONG_AWS_ACCOUNT")
    st_row, st = preview.outputs(c["cloudformation"], ST)
    _, prod = preview.outputs(c["cloudformation"], PROD)
    require(st.get("CandidateDataBucket") == preview.ST_BUCKET and
            prod.get("CandidateDataBucket") == preview.PROD_BUCKET,
            "ST_PROD_BUCKET_MISMATCH")
    for key in preview.RULES:
        expected_st = "DISABLED" if key == "CandidateOrchestratorRuleName" else "ENABLED"
        require(c["events"].describe_rule(Name=st[key]).get("State") == expected_st,
                "ST_RULE_STATE_MISMATCH:" + key)
        require(c["events"].describe_rule(Name=prod[key]).get("State") == "DISABLED",
                "PROD_RULE_MUST_BE_OFF:" + key)
    params = {p["ParameterKey"]: p.get("ParameterValue") for p in
              st_row.get("Parameters", [])}
    require(params.get("CandidateSignalScheduleState") == "DISABLED" and
            params.get("ExpectedSchedulerState") == "DISABLED" and
            params.get("MonitoringStartSession") == "2026-10-30",
            "CFN_PARAMETERS_REQUIRE_SEPARATE_DRIFT_REVIEW")
    artifact_bucket = params.get("ArtifactBucket")
    artifact_key = params.get("ArtifactKey")
    require(artifact_bucket and artifact_key and not any(
        term in artifact_key.lower() for term in ("latest", "current")),
        "SOURCE_ARTIFACT_NOT_IMMUTABLY_KEYED")
    expected_logical = {}
    functions = {}
    for output_key in LAMBDA_OUTPUT_KEYS:
        function_name = st.get(output_key)
        require(bool(function_name) and function_name.startswith(ST + "-"),
                "UNEXPECTED_ST_LAMBDA_OUTPUT:" + output_key)
        cfg = c["lambda"].get_function_configuration(FunctionName=function_name)
        require(cfg.get("State") == "Active" and
                cfg.get("LastUpdateStatus") == "Successful",
                "ST_LAMBDA_NOT_READY:" + output_key)
        require(cfg.get("CodeSha256") in (OLD_SHA_B64, LOCAL_CANDIDATE_SHA_B64),
                "UNRECOGNIZED_ST_LAMBDA_CODE:" + output_key)
        functions[function_name] = cfg.get("CodeSha256")
    require(len(functions) == 5, "ST_LAMBDA_NOT_UNIQUE")
    for row in c["cloudformation"].list_stack_resources(StackName=ST).get(
            "StackResourceSummaries", []):
        if row.get("ResourceType") == "AWS::Lambda::Function" and row.get(
                "PhysicalResourceId") in functions:
            expected_logical[row["LogicalResourceId"]] = row["PhysicalResourceId"]
    require(len(expected_logical) == 5, "CFN_LAMBDA_RESOURCE_MAPPING_INCOMPLETE")
    return {
        "st_outputs": st, "prod_outputs": prod,
        "parameters": params, "source_artifact_bucket": artifact_bucket,
        "source_artifact_key": artifact_key,
        "lambdas": functions, "expected_lambda_resources": expected_logical,
        "st_schedule_states": {key: "DISABLED" if key == "CandidateOrchestratorRuleName"
                               else "ENABLED" for key in preview.RULES},
        "prod_schedules_all_disabled": True,
    }


def planned_key(state):
    source = state["source_artifact_key"]
    parent = source.rsplit("/", 1)[0] if "/" in source else ""
    sha = base64.b64decode(LOCAL_CANDIDATE_SHA_B64).hex()
    filename = "stocklens-st-paper-" + sha + ".zip"
    return (parent + "/" if parent else "") + filename


def verify_staged_artifact(c, state):
    bucket = state["source_artifact_bucket"]
    key = planned_key(state)
    meta = c["s3"].head_object(Bucket=bucket, Key=key)
    require(meta.get("ContentLength", 0) > 0 and
            meta.get("Metadata", {}).get("stocklens-sha256-b64") ==
            LOCAL_CANDIDATE_SHA_B64,
            "STAGED_ARTIFACT_METADATA_CHANGED")
    data = c["s3"].get_object(Bucket=bucket, Key=key)["Body"].read(preview.ZIP_SIZE_LIMIT + 1)
    require(digest(data) == LOCAL_CANDIDATE_SHA_B64, "STAGED_ARTIFACT_BYTES_DIFFER")
    return {"artifact_sha256_verified": True,
            "artifact_versioned": meta.get("VersionId") not in (None, "null", "")}


def change_set_parameters(state):
    params = state["parameters"]
    require("ArtifactKey" in params, "ARTIFACT_KEY_PARAMETER_ABSENT")
    result = []
    for name in sorted(params):
        if name == "ArtifactKey":
            result.append({"ParameterKey": name, "ParameterValue": planned_key(state)})
        else:
            result.append({"ParameterKey": name, "UsePreviousValue": True})
    return result


def validate_change_set(desc, state):
    require(desc.get("StackName") == ST and
            desc.get("ChangeSetName") == CHANGE_NAME and
            desc.get("Status") == "CREATE_COMPLETE" and
            desc.get("ExecutionStatus") == "AVAILABLE" and not desc.get("NextToken"),
            "UNREVIEWED_OR_UNAVAILABLE_CHANGE_SET")
    params = {p["ParameterKey"]:p for p in desc.get("Parameters", [])}
    require(params.get("ArtifactKey", {}).get("ParameterValue") == planned_key(state),
            "CHANGE_SET_ARTIFACT_KEY_CHANGED")
    for name, value in state["parameters"].items():
        if name != "ArtifactKey":
            item = params.get(name, {})
            # CloudFormation describe-change-set often resolves UsePreviousValue
            # into a concrete ParameterValue; require exact equality either way.
            require(item.get("UsePreviousValue") is True or item.get("ParameterValue") == value,
                    "UNAPPROVED_PARAMETER_CHANGE:" + name)
    expected = set(state["expected_lambda_resources"])
    changes = desc.get("Changes", [])
    seen = set()
    for item in changes:
        rc = item.get("ResourceChange", {})
        lid = rc.get("LogicalResourceId")
        require(lid in expected and lid not in seen,
                "UNEXPECTED_CFN_RESOURCE_CHANGE:" + str(lid))
        require(rc.get("ResourceType") == "AWS::Lambda::Function" and
                rc.get("Action") == "Modify" and
                rc.get("Replacement") in ("False", False, None),
                "CFN_LAMBDA_REPLACEMENT_OR_UNEXPECTED_ACTION:" + str(lid))
        # CloudFormation ChangeSet details must prove Code was the only
        # changed property. No Environment/IAM/Version/EventBridge changes.
        details = rc.get("Details", [])
        require(bool(details), "CFN_LAMBDA_CHANGE_DETAILS_UNVERIFIED:" + lid)
        for d in details:
            target = d.get("Target", {})
            require(target.get("Attribute") == "Properties" and
                    target.get("Name") == "Code" and
                    target.get("RequiresRecreation") in (None, "Never") and
                    d.get("ChangeSource") in ("ParameterReference", "DirectModification",
                                              "Automatic"),
                    "CFN_CHANGE_NOT_CODE_ONLY:" + lid)
        seen.add(lid)
    require(seen == expected, "CFN_CHANGED_LAMBDAS_NOT_EXACT_FIVE")
    return sorted(seen)



def review_existing_change_set(c):
    """Read existing ST change set without creating, executing or deleting it.

    CloudFormation may emit multiple Details for the same target, including
    ParameterReference + Dynamic/Static pairs. Preserve every field necessary
    to diagnose why the strict Code-only gate rejected the change, but never
    print BeforeValue, AfterValue, full template or artifact/S3 coordinates.
    """
    state = safe_state(c)
    cf = c["cloudformation"]
    rows = []
    first = None
    next_token = None
    for page in range(10):
        request = {"StackName": ST, "ChangeSetName": CHANGE_NAME}
        if next_token:
            request["NextToken"] = next_token
        result = cf.describe_change_set(**request)
        if first is None:
            first = result
        else:
            require(result.get("StackName") == first.get("StackName") and
                    result.get("ChangeSetName") == first.get("ChangeSetName"),
                    "CFN_CHANGE_SET_PAGINATION_DRIFT")
        rows.extend(result.get("Changes", []))
        next_token = result.get("NextToken")
        if not next_token:
            break
    else:
        raise RuntimeError("CFN_CHANGE_SET_MORE_THAN_TEN_PAGES_REVIEW_IN_CONSOLE")
    desc = {**first, "Changes": rows, "NextToken": None}
    try:
        verified = validate_change_set(desc, state)
        verdict = "EXACT_FIVE_CODE_ONLY_VALIDATED_NOT_EXECUTED"
        reason = None
    except Exception as exc:
        verdict = "BLOCKED_PENDING_MANUAL_REVIEW"
        reason = str(exc)[:170]
        verified = []
    summary = []
    for item in rows:
        rc = item.get("ResourceChange", {})
        details = []
        for d in rc.get("Details", []):
            target = d.get("Target") or {}
            causing = str(d.get("CausingEntity") or "")
            # CausingEntity normally contains a parameter/resource name. Do not
            # disclose unexpected text, ARN, external URL or secret-like values.
            if causing and not (len(causing) <= 90 and
                                causing.replace("_", "").replace("-", "").isalnum()):
                causing = "REDACTED"
            details.append({
                "attribute": target.get("Attribute"),
                "property": target.get("Name"),
                "recreation": target.get("RequiresRecreation"),
                "evaluation": d.get("Evaluation"),
                "source": d.get("ChangeSource"),
                "causing_entity": causing or None,
            })
        summary.append({
            "logical_id": rc.get("LogicalResourceId"),
            "type": rc.get("ResourceType"),
            "action": rc.get("Action"),
            "replacement": rc.get("Replacement"),
            "scope": rc.get("Scope", []),
            "details": details,
        })
    return {
        "status": verdict,
        "validator_block_reason": reason,
        "change_set_name": CHANGE_NAME,
        "change_set_status": first.get("Status"),
        "change_set_execution_status": first.get("ExecutionStatus"),
        "change_count": len(rows),
        "resource_changes": summary,
        "validated_lambda_code_resources": verified,
        "signal_schedule_parameter_drift_still_present": True,
        "prod_schedules_all_disabled": True,
        "lambda_code_unchanged_by_this_review": True,
        "change_set_executed": False,
        "aws_mutations": False,
        "paper_backfill": False,
        "broker_orders": False,
        "warning": "Do not run apply until Code-only proof is accepted and approved.",
    }


def inspect(c):
    state = safe_state(c)
    current = set(state["lambdas"].values())
    require(len(current) == 1, "PARTIAL_LAMBDA_DEPLOYMENT_REVIEW_REQUIRED")
    return {"status":"READ_ONLY_ST_RELEASE_INSPECTION",
            "live_code_sha256_b64": list(current)[0],
            "candidate_code_sha256_b64": LOCAL_CANDIDATE_SHA_B64,
            "artifact_key_fingerprint": hashlib.sha256(
                planned_key(state).encode()).hexdigest(),
            "cloudformation_schedule_parameter_drift": True,
            "st_schedule_states": state["st_schedule_states"],
            "prod_schedules_all_disabled": True,
            "deployment_executed": False, "broker_orders": False}


def prepare(c):
    state = safe_state(c)
    require(set(state["lambdas"].values()) == {OLD_SHA_B64},
            "ST_CODE_BASELINE_CHANGED_OR_PARTIAL_DEPLOYMENT")
    candidate = candidate_bytes()
    key = planned_key(state)
    bucket = state["source_artifact_bucket"]
    original_meta = c["s3"].head_object(
        Bucket=bucket, Key=state["source_artifact_key"])
    require(original_meta.get("ContentLength", 0) > 0,
            "SOURCE_ARTIFACT_NOT_FOUND")
    # Persist new immutable blob under a *new* content-addressed object key.
    # This does NOT change any running Lambda or EventBridge rule.
    try:
        existing = c["s3"].head_object(Bucket=bucket, Key=key)
        require(existing.get("Metadata", {}).get("stocklens-sha256-b64") ==
                LOCAL_CANDIDATE_SHA_B64,
                "CONTENT_ADDRESSED_KEY_COLLISION")
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if str(code) not in ("404", "NoSuchKey", "NotFound"):
            raise
        args = {
            "Bucket": bucket, "Key": key, "Body": candidate, "IfNoneMatch": "*",
            "Metadata": {"stocklens-sha256-b64": LOCAL_CANDIDATE_SHA_B64},
        }
        if original_meta.get("ServerSideEncryption") in ("AES256", "aws:kms"):
            args["ServerSideEncryption"] = original_meta["ServerSideEncryption"]
            if original_meta.get("SSEKMSKeyId"):
                args["SSEKMSKeyId"] = original_meta["SSEKMSKeyId"]
        c["s3"].put_object(**args)
    verify_staged_artifact(c,state)
    cf = c["cloudformation"]
    cf.create_change_set(
        StackName=ST, ChangeSetName=CHANGE_NAME, ChangeSetType="UPDATE",
        UsePreviousTemplate=True, Parameters=change_set_parameters(state),
        Capabilities=["CAPABILITY_IAM","CAPABILITY_NAMED_IAM"],
        Description="ST-only: Code-only five-Lambda update to audited immutable ZIP;"
                    " all EventBridge rules and PROD unchanged")
    for _ in range(40):
        desc = cf.describe_change_set(StackName=ST,ChangeSetName=CHANGE_NAME)
        if desc.get("Status") in ("CREATE_COMPLETE", "FAILED"):
            break
        time.sleep(2)
    else:
        raise RuntimeError("CHANGE_SET_NOT_READY_INSPECT_WITHOUT_RETRY_MUTATIONS")
    changed = validate_change_set(desc,state)
    return {"status":"ST_ONLY_CHANGE_SET_PREPARED_NOT_EXECUTED",
            "name": CHANGE_NAME,"lambda_resources":changed,
            "new_artifact_sha256_b64":LOCAL_CANDIDATE_SHA_B64,
            "live_trading_schedules_untouched": True,
            "cfn_parameter_drift_remains": True,
            "prod_changes": False, "broker_orders": False,
            "aws_mutations": "S3_NEW_IMMUTABLE_ARTIFACT_AND_CFN_CHANGE_SET_ONLY",
            "execution": False}


def apply(c, *, approved=False):
    require(approved, "REQUIRES_EXPLICIT_--yes_FOR_LIVE_ST_LAMBDA_DEPLOY")
    state = safe_state(c)
    require(set(state["lambdas"].values()) == {OLD_SHA_B64},
            "BASELINE_CHANGED_OR_DEPLOY_PARTIAL_INSPECT_FIRST")
    # Candidate ZIP must still match local audited source AND S3 bytes.
    require(digest(candidate_bytes()) == LOCAL_CANDIDATE_SHA_B64,
            "LOCAL_CANDIDATE_CHANGED")
    verify_staged_artifact(c,state)
    desc = c["cloudformation"].describe_change_set(
        StackName=ST,ChangeSetName=CHANGE_NAME)
    reviewed = validate_change_set(desc,state)
    print("EXACT_ST_CODE_ONLY_CFN_CHANGES:",json.dumps(reviewed),flush=True)
    print("EXPLICIT_APPROVAL_RECEIVED:EXECUTE_ST_ONLY_CFN",flush=True)
    c["cloudformation"].execute_change_set(
        StackName=ST,ChangeSetName=CHANGE_NAME)
    for _ in range(95):
        status = c["cloudformation"].describe_stacks(StackName=ST)["Stacks"][0]["StackStatus"]
        if status in ("UPDATE_COMPLETE", "UPDATE_ROLLBACK_COMPLETE",
                      "UPDATE_FAILED", "UPDATE_ROLLBACK_FAILED"):
            break
        time.sleep(4)
    else:
        raise RuntimeError("CFN_UPDATE_STILL_RUNNING_NEEDS_MANUAL_REVIEW")
    require(status == "UPDATE_COMPLETE", "CFN_DEPLOY_NOT_SUCCESSFUL:" + status)
    final = safe_state(c)
    require(set(final["lambdas"].values()) == {LOCAL_CANDIDATE_SHA_B64},
            "ST_FIVE_LAMBDA_CODE_PARITY_NOT_VERIFIED")
    return {"status":"ST_ONLY_LAMBDA_CODE_DEPLOYED",
            "lambda_count":5, "sha256_b64":LOCAL_CANDIDATE_SHA_B64,
            "st_schedules_preserved":True, "prod_schedules_all_disabled":True,
            "paper_2026_11_05":"NOT_QUALIFIED_DO_NOT_BACKFILL",
            "fresh_forward_paper_receipts":"NOT_YET_PROVEN",
            "broker_orders":False,"prod_changes":False}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("mode", choices=("inspect","review","prepare","apply"))
    ap.add_argument("--yes",action="store_true",
                    help="Explicit approval to execute previously reviewed ST-only change set")
    args=ap.parse_args()
    require(not args.yes or args.mode=="apply",
            "--yes_ALLOWED_ONLY_IN_apply")
    import boto3
    c=sdk_clients(boto3)
    if args.mode=="inspect": result=inspect(c)
    elif args.mode=="review": result=review_existing_change_set(c)
    elif args.mode=="prepare": result=prepare(c)
    else: result=apply(c,approved=args.yes)
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({"status":"BLOCKED_REVIEW_REQUIRED",
                          "reason":str(exc)[:300],
                          "prod_changes":False,"broker_orders":False,
                          "paper_backfill":False}))
        sys.exit(2)

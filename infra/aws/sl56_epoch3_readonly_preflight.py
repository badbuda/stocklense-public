#!/usr/bin/env python3
"""SL-56 new ST Paper epoch 2026-11-12 — read-only factual AWS preflight.

No Lambda invoke, no S3 PUT, no EventBridge changes, no old alarm clears, no
broker. A PASS allows planning only; it NEVER authorizes genesis/receipts.
Must not claim that future Nov12 execution data or capital are approved.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
import sys

from stocklens import paper_epoch3 as epoch

ACCOUNT="634740393398"
REGION="eu-central-1"
ST="stocklens-st"
PROD="stocklens-prod"
BUCKET="stocklens-st-candidatedata-6jj7i9fxjmfr"
PROD_BUCKET="stocklens-prod-candidatedata-c3yge4ymwb7u"
SIGNAL_CODE_SHA_B64="hThsoR3Fk9/uRxZn0xHI6wlHWSR4hTzKXqGbss7PQuI="


def require(ok, code):
    if not ok:
        raise RuntimeError(code)


def stack_outputs(client, name):
    rows=client.describe_stacks(StackName=name)["Stacks"]
    require(len(rows)==1 and rows[0]["StackStatus"] in ("CREATE_COMPLETE","UPDATE_COMPLETE"),
            "CLOUDFORMATION_STACK_NOT_STABLE:"+name)
    return {e["OutputKey"]:e["OutputValue"] for e in rows[0].get("Outputs",[])}


def current_version(s3, key, *, required):
    try:
        head=s3.head_object(Bucket=BUCKET,Key=key)
    except Exception as exc:
        error=(getattr(exc,"response",{}) or {}).get("Error",{}).get("Code","")
        marker=((getattr(exc,"response",{}) or {}).get("ResponseMetadata",{})
                .get("HTTPHeaders",{}).get("x-amz-delete-marker"))
        if error in ("404","NotFound","NoSuchKey") and marker not in (True,"true","True"):
            require(not required,"REQUIRED_S3_OBJECT_MISSING:"+key)
            return None
        raise RuntimeError("OBJECT_HEAD_FAILED_OR_DELETE_MARKER:"+key+":"+str(error)) from exc
    ver=head.get("VersionId")
    require(ver not in (None,"","null") and
            type(head.get("ContentLength")) is int and
            2 <= head["ContentLength"] <= 1_000_000,
            "S3_VERSIONED_HEAD_INVALID:"+key)
    try:
        obj=s3.get_object(Bucket=BUCKET,Key=key,VersionId=ver)
        raw=obj["Body"].read(1_000_001)
    except Exception as exc:
        raise RuntimeError("S3_VERSION_PINNED_READ_FAILED:"+key) from exc
    require(len(raw)==head["ContentLength"] and obj.get("VersionId")==ver,
            "S3_VERSIONED_BODY_MISMATCH:"+key)
    return {"sha256":hashlib.sha256(raw).hexdigest(),
            "versioned":True, "last_modified":head.get("LastModified"),
            "raw":raw}


def preflight(c):
    sts, cf, ev, lam, s3=(c[k] for k in ("sts","cloudformation","events","lambda","s3"))
    require(sts.get_caller_identity()["Account"]==ACCOUNT,"WRONG_AWS_ACCOUNT")
    st, prod=stack_outputs(cf,ST),stack_outputs(cf,PROD)
    require(st["CandidateDataBucket"]==BUCKET and
            prod["CandidateDataBucket"]==PROD_BUCKET and
            BUCKET!=PROD_BUCKET,"ST_PROD_BUCKET_ISOLATION_MISMATCH")
    require(s3.get_bucket_versioning(Bucket=BUCKET).get("Status")=="Enabled",
            "S3_VERSIONING_NOT_ENABLED")
    for k in ("CandidateSignalOnlyRuleName","CandidatePaperOnlyRuleName",
              "CandidateOrchestratorRuleName"):
        require(ev.describe_rule(Name=prod[k]).get("State")=="DISABLED",
                "PRODUCTION_SCHEDULE_ENABLED:"+k)
    signal=lam.get_function_configuration(FunctionName=st["CandidateFunctionName"])
    require(signal.get("State")=="Active" and
            signal.get("LastUpdateStatus")=="Successful" and
            signal.get("CodeSha256")==SIGNAL_CODE_SHA_B64,
            "LATEST_ST_SIGNAL_PATCH_NOT_VERIFIED")
    # The OLD Paper scheduler still exists; do not silently disable it.
    paper_rule=ev.describe_rule(Name=st["CandidatePaperOnlyRuleName"])
    require(paper_rule.get("State")=="ENABLED",
            "EXISTING_PAPER_SCHEDULE_STATE_CHANGED_REVIEW")
    old={}
    for key, sha in epoch.HISTORIC_SHA256.items():
        actual=current_version(s3,key,required=True)
        require(actual["sha256"]==sha,"OLD_BOOK_PIN_CHANGED:"+key)
        old[key]={"sha256":sha,"s3_versioned":True}
    # Old gap must NOT suddenly become qualified, e.g. from a new writer.
    absence={}
    for day in epoch.MISSED:
        for typ in ("sessions","continuity"):
            key=f"paper/{typ}/{day}.json"
            obj=current_version(s3,key,required=False)
            require(obj is None,"OLD_BOOK_GAP_CHANGED_NEEDS_FORENSICS:"+key)
            absence[key]="ABSENT_VERIFIED"
    new_genesis=current_version(s3,epoch.NEW_PREFIX+"genesis.json",required=False)
    require(new_genesis is None,"NEW_BOOK_GENESIS_ALREADY_EXISTS_REVIEW")
    prior_signal=current_version(
        s3,f"signals/{epoch.PREVIOUS_SIGNAL_DAY}.json",required=False)
    if prior_signal is not None:
        report=json.loads(prior_signal["raw"])
        require(report.get("mode")=="SHADOW_ONLY_NO_BROKER_ACTIONS" and
                report.get("latest",{}).get("asof_date")==epoch.PREVIOUS_SIGNAL_DAY and
                report.get("execution_plan",{}).get("broker_actions_enabled") is False,
                "PRIOR_SIGNAL_NOT_FROZEN_SHADOW")
        stamp=prior_signal["last_modified"]
        require(isinstance(stamp,datetime) and stamp.tzinfo is not None
                and datetime(2026,11,11,21,tzinfo=timezone.utc)<=stamp.astimezone(timezone.utc)
                < datetime(2026,11,12,14,30,tzinfo=timezone.utc),
                "PRIOR_SIGNAL_ARCHIVE_NOT_PREOPEN_OR_AFTER_PRIOR_CLOSE")
    return {
        "status":"ST_EPOCH3_READONLY_PREPARE_CHECK_PASS_NOT_DEPLOYMENT",
        "checked_utc":datetime.now(timezone.utc).isoformat(),
        "old_epoch_last_qualified":epoch.LAST_OLD_DAY,
        "old_epoch_historic_sha_pins":old,
        "old_book_gaps_still_absent":list(epoch.MISSED),
        "new_book":epoch.NEW_BOOK,
        "new_prefix":epoch.NEW_PREFIX,
        "proposed_first_market_session":epoch.FIRST_NEW_DAY,
        "prior_signal":("VERSIONED_VERIFIED" if prior_signal is not None
                       else "NOT_YET_ARCHIVED_WAIT_FOR_SCHEDULE"),
        "fresh_execution_1m_data_verified":False,
        "independent_model_engine_connected":False,
        "watchdog_new_epoch_monitoring_connected":False,
        "operator_preopen_inception_approval_recorded":False,
        "new_genesis_present":False,
        "old_book_and_original_alarms_preserved":True,
        "production_all_schedules_disabled":True,
        "aws_mutations":False,
        "broker_orders":False,
        "deployment_authorized":False
    }


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--inspect",action="store_true")
    args=p.parse_args(argv)
    require(args.inspect,"MUST_USE_--inspect_READ_ONLY")
    import boto3
    session=boto3.Session(region_name=REGION)
    c={k:session.client(k) for k in ("sts","cloudformation","events","lambda","s3")}
    report=preflight(c)
    print(json.dumps(report,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status":"ST_EPOCH3_PREFLIGHT_BLOCKED_NO_MUTATIONS",
                          "reason_type":type(exc).__name__,
                          "reason":str(exc)[:260],
                          "aws_mutations":False,"broker_orders":False,
                          "deployment_authorized":False}))
        raise SystemExit(2)

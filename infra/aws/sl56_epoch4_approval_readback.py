#!/usr/bin/env python3
"""Verify exact operator-written ST Epoch4 preopen approval in real S3; READ ONLY.

This does not create Genesis, fabricate Paper, invoke Lambda, deploy code,
acknowledge alarms, trigger schedules, mutate PROD or connect a broker.
The original preopen S3 approval timestamp is checked independently of
the *current* time, so this can run after NYSE open without backdating.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone
from infra.aws import sl56_future_paper_inception as p

BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH4_20261119"
PREFIX = "paper/epochs/" + BOOK + "/"
KEY = PREFIX + "preopen-inception-approval.json"
EXPECTED_SHA256 = "a7a0bf04760aa3d7ca83117b434bc13e7a63db785caff190123339a331afd27d"
EXPECTED_SIGNAL_SHA256 = "0da918b19c00449a8d636a97dc5b0b1fac6999a32fa39e756365be017eeb5008"
EXPECTED_SIGNAL_VERSION = "BKGBblRPD3SuORUQsUzIgnBFFRAIGvBq"


def inspect(c):
    p.require(c["sts"].get_caller_identity().get("Account") == p.ACCOUNT,
              "WRONG_AWS_ACCOUNT")
    st, prod = p.stack(c["cloudformation"], p.ST), p.stack(c["cloudformation"], p.PROD)
    p.require(st.get("CandidateDataBucket")==p.BUCKET and
              prod.get("CandidateDataBucket")==p.PROD_BUCKET,
              "ST_PROD_ISOLATION_CHANGED")
    p.require(c["s3"].get_bucket_versioning(Bucket=p.BUCKET).get("Status")=="Enabled",
              "BUCKET_VERSIONING_DISABLED")
    rules = {}
    for key, state in p.REQUIRED_ST_RULES.items():
        actual = c["events"].describe_rule(Name=st[key]).get("State")
        p.require(actual==state,"ST_SCHEDULE_UNEXPECTED:"+key)
        p.require(c["events"].describe_rule(Name=prod[key]).get("State")=="DISABLED",
                  "PROD_SCHEDULE_ENABLED:"+key)
        rules[key]=actual
    for key, sha, handler in (
        ("CandidateFunctionName",p.SIGNAL_SHA,"infra.aws.independent_pipeline.handler"),
        ("CandidatePaperFunctionName",p.PAPER_SHA,"infra.aws.independent_paper.handler"),
    ):
        fn=c["lambda"].get_function_configuration(FunctionName=st[key])
        p.require(fn.get("State")=="Active" and
                  fn.get("LastUpdateStatus")=="Successful" and
                  fn.get("CodeSha256")==sha and fn.get("Handler")==handler and
                  fn.get("Environment",{}).get("Variables",{}).get("STOCKLENS_DATA_BUCKET")==p.BUCKET,
                  "DEPLOYED_CODE_CHANGED:"+key)
    for key, expected in p.OLD_PINS.items():
        _,body,digest=p.immutable_json(c["s3"],key)
        p.require(isinstance(body,dict) and digest==expected,
                  "OLD_BOOK_HASH_MISMATCH:"+key)
    approval_head, approval, digest=p.immutable_json(c["s3"],KEY)
    p.require(digest==EXPECTED_SHA256,
              "APPROVAL_CONTENT_SHA_CHANGED")
    version=approval_head.get("VersionId")
    p.require(isinstance(version,str) and version not in ("","null"),
              "APPROVAL_VERSION_MISSING")
    p.require((approval_head.get("Metadata") or {}).get("sha256")==digest,
              "APPROVAL_METADATA_SHA_INVALID")
    prev, close, opening = p.xcalendar(date(2026,11,19))
    p.require(prev=="2026-11-18","PREVIOUS_MARKET_SESSION_MISMATCH")
    approved_at = p.utc(approval_head.get("LastModified"))
    p.require(close<opening and approved_at<opening,
              "APPROVAL_NOT_VERIFIED_PREOPEN")
    signal_head, signal, signal_sha=p.immutable_json(
        c["s3"], "signals/2026-11-18.json")
    p.require(signal_head.get("VersionId")==EXPECTED_SIGNAL_VERSION and
              signal_sha==EXPECTED_SIGNAL_SHA256,
              "APPROVAL_PRIOR_SIGNAL_SOURCE_CHANGED")
    signal_saved=p.utc(signal_head.get("LastModified"))
    p.require(close<=signal_saved<approved_at and signal_saved<opening,
              "APPROVED_SIGNAL_NOT_AVAILABLE_PREOPEN")
    p.require(signal.get("mode")=="SHADOW_ONLY_NO_BROKER_ACTIONS" and
              signal.get("latest",{}).get("asof_date")==prev and
              signal.get("execution_plan",{}).get("broker_actions_enabled") is False,
              "APPROVED_SIGNAL_WRONG_MODE")
    expected={
       "schema":"stocklens-epoch4-preopen-inception-intent-v1",
       "book":BOOK,"first_session":"2026-11-19",
       "prior_signal_key":"signals/2026-11-18.json",
       "prior_signal_version_id":EXPECTED_SIGNAL_VERSION,
       "prior_signal_sha256":EXPECTED_SIGNAL_SHA256,
       "starting_cash_usd":100000.0,"starting_shares":{"QQQ":0,"TQQQ":0},
       "old_nav_transferred":False,
       "old_book_last_qualified":p.PRIOR_LAST_QUALIFIED,
       "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
       "broker_orders_authorized":False,
       "genesis_created":False,"paper_trades_created":False,
    }
    p.require(approval==expected,
              "APPROVAL_RECORD_FIELDS_MISMATCH")
    # Evidence from exact S3 version history; current delete marker or more
    # than one approval version requires manual review, no silent acceptance.
    result=c["s3"].list_object_versions(
        Bucket=p.BUCKET,Prefix=KEY,MaxKeys=1000)
    p.require(result.get("IsTruncated") is not True and
              not result.get("DeleteMarkers"),
              "APPROVAL_VERSION_INVENTORY_INCOMPLETE_OR_DELETED")
    versions=[v for v in result.get("Versions",[]) if v.get("Key")==KEY]
    p.require(len(versions)==1 and versions[0].get("IsLatest") is True and
              versions[0].get("VersionId")==version,
              "APPROVAL_NOT_UNIQUE_LATEST_VERSION")
    return {
        "status":"APPROVED_PREOPEN_EPOCH4_INTENT_S3_VERIFIED_NOT_PAPER_RECOVERY",
        "book":BOOK, "approval_key":KEY,
        "approval_version_id":version, "approval_sha256":digest,
        "approval_s3_timestamp_utc":approved_at.isoformat(),
        "prior_signal_sha256":signal_sha,
        "prior_signal_version_id":signal_head["VersionId"],
        "opening_utc":opening.isoformat(),
        "starting_simulated_cash_usd":100000.0,
        "old_book_anchors_unchanged":True,
        "prod_schedules_disabled":True,
        "old_st_paper_scheduler_disabled":True,
        "new_genesis_checked_or_created":False,
        "new_paper_runtime_deployed":False,
        "paper_trades_created":False,
        "old_alarm_history_preserved":True,
        "aws_mutations":False, "lambda_invocations":False,
        "broker_orders":False
    }


def main():
    import boto3
    session=boto3.session.Session(region_name=p.REGION)
    c={k:session.client(k) for k in
       ("sts","cloudformation","events","lambda","s3")}
    try:
        print(json.dumps(inspect(c),indent=2,sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"status":"EPOCH4_APPROVAL_UNVERIFIED_STOP",
                          "error_type":type(exc).__name__,
                          "reason":str(exc)[:220],
                          "aws_mutations":False,"broker_orders":False}))
        return 2


if __name__=="__main__":
    raise SystemExit(main())

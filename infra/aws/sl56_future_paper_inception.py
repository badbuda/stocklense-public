#!/usr/bin/env python3
"""ST-only next-eligible Paper inception. Inspection by default, explicit approval only.

This does NOT deploy a new Paper Lambda, generate fills, alter old book,
acknowledge alarms, or enable EventBridge. It creates at most ONE immutable
preopen *intent* object for a NEW, isolated, independent simulated $100k book.
A prospective Paper engine and its epoch-scoped watchdog are still required.

Historical Paper after 2026-11-04 is NOT reconstructed. A signal must have
been frozen into versioned S3 AFTER the previous NYSE close and BEFORE first
NYSE open. Both wall clock and S3 server timestamp must precede that open.
"""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import math
import sys

ACCOUNT = "634740393398"
REGION = "eu-central-1"
ST, PROD = "stocklens-st", "stocklens-prod"
BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
PROD_BUCKET = "stocklens-prod-candidatedata-c3yge4ymwb7u"
FIRST_ALLOWED = date(2026, 11, 19)
PRIOR_LAST_QUALIFIED = "2026-11-04"
SIGNAL_SHA = "hThsoR3Fk9/uRxZn0xHI6wlHWSR4hTzKXqGbss7PQuI="
PAPER_SHA = "YKpLN8Ks36blX4J9z+GnDKx9fCN87tA7wwc5Sc/25WQ="
REQUIRED_ST_RULES = {
    "CandidateSignalOnlyRuleName":"ENABLED",
    "CandidatePaperOnlyRuleName":"DISABLED",
    "CandidateOrchestratorRuleName":"DISABLED",
}
OLD_PINS = {
    "paper/book/NEW_AWS_INDEPENDENT_STAGING_BOOK/genesis.json":
        "355398c0e93b9ea0aeb17f71fb90e4f040156314bff6eaf4fba3f3297c8cd8e1",
    "paper/sessions/2026-11-04.json":
        "797bccafa9aba7b3799c312bbd1ed2f67e0101c127f2bcbdec6318d91f2f22d2",
    "paper/continuity/2026-11-04.json":
        "92d39a078d1859b0f1870826b89eb093d610dcb279696b778ce4b8d709db6eae",
}
MAX_BYTES = 2_000_000


def require(condition, code):
    if not condition:
        raise RuntimeError(code)


def utc(ts):
    require(isinstance(ts, datetime) and ts.tzinfo is not None,
            "NAIVE_OR_MISSING_TIME")
    return ts.astimezone(timezone.utc)


def stack(cf, name):
    rows = cf.describe_stacks(StackName=name).get("Stacks", [])
    require(len(rows) == 1 and rows[0].get("StackStatus") in (
        "CREATE_COMPLETE","UPDATE_COMPLETE"), "STACK_UNSTABLE:" + name)
    return {x["OutputKey"]: x["OutputValue"] for x in rows[0]["Outputs"]}


def xcalendar(first):
    import exchange_calendars as x
    cal = x.get_calendar("XNYS")
    require(first >= FIRST_ALLOWED and cal.is_session(first.isoformat()),
            "INELIGIBLE_NEW_EXCHANGE_DAY")
    first_str = first.isoformat()
    previous = cal.previous_session(first_str).date().isoformat()
    opening = utc(cal.session_open(first_str).to_pydatetime())
    prior_close = utc(cal.session_close(previous).to_pydatetime())
    return previous, prior_close, opening


def immutable_json(s3, key):
    head = s3.head_object(Bucket=BUCKET, Key=key)
    version = head.get("VersionId")
    size = head.get("ContentLength")
    require(isinstance(version,str) and version not in ("", "null") and
            type(size) is int and 2 <= size <= MAX_BYTES,
            "UNVERSIONED_OR_OVERSIZED_S3_OBJECT:" + key)
    response = s3.get_object(Bucket=BUCKET, Key=key, VersionId=version)
    raw = response["Body"].read(MAX_BYTES + 1)
    require(response.get("VersionId") == version and len(raw) == size,
            "VERSIONED_READ_MISMATCH:" + key)
    return head, json.loads(raw), hashlib.sha256(raw).hexdigest()


def version_inventory(s3, prefix):
    """Check ANY old version/deletion beneath fresh new prefix: fail closed."""
    args = {"Bucket":BUCKET,"Prefix":prefix,"MaxKeys":1000}
    for _ in range(10):
        result=s3.list_object_versions(**args)
        require(not result.get("Versions") and not result.get("DeleteMarkers"),
                "NEW_EPOCH_PREFIX_ALREADY_HAS_HISTORY_REVIEW_REQUIRED")
        if not result.get("IsTruncated"):
            return
        require(bool(result.get("NextKeyMarker")) and
                bool(result.get("NextVersionIdMarker")),
                "NEW_EPOCH_PREFIX_VERSION_INVENTORY_UNVERIFIED")
        args["KeyMarker"]=result["NextKeyMarker"]
        args["VersionIdMarker"]=result["NextVersionIdMarker"]
    raise RuntimeError("NEW_EPOCH_PREFIX_INVENTORY_PAGE_CAP")


def check(clients, first, now):
    """Authenticate all safety conditions before an operator can approve."""
    require(clients["sts"].get_caller_identity().get("Account") == ACCOUNT,
            "WRONG_ACCOUNT")
    prev, prev_close, opening = xcalendar(first)
    require(utc(now) < opening, "PREOPEN_DEADLINE_PASSED_NO_BACKDATING")
    cf,events,lam,s3 = (clients[k] for k in
                        ("cloudformation","events","lambda","s3"))
    st,prod=stack(cf,ST),stack(cf,PROD)
    require(st.get("CandidateDataBucket")==BUCKET and
            prod.get("CandidateDataBucket")==PROD_BUCKET,
            "ST_PROD_ISOLATION_MISMATCH")
    require(s3.get_bucket_versioning(Bucket=BUCKET).get("Status")=="Enabled",
            "ST_BUCKET_NOT_VERSIONED")
    for key,state in REQUIRED_ST_RULES.items():
        require(events.describe_rule(Name=st[key]).get("State")==state,
                "ST_SCHEDULE_UNEXPECTED:"+key)
        require(events.describe_rule(Name=prod[key]).get("State")=="DISABLED",
                "PRODUCTION_SCHEDULE_ENABLED:"+key)
    for fn, sha, handler in (
        ("CandidateFunctionName",SIGNAL_SHA,"infra.aws.independent_pipeline.handler"),
        ("CandidatePaperFunctionName",PAPER_SHA,"infra.aws.independent_paper.handler"),
    ):
        cfg=lam.get_function_configuration(FunctionName=st[fn])
        require(cfg.get("State")=="Active" and
                cfg.get("LastUpdateStatus")=="Successful" and
                cfg.get("CodeSha256")==sha and cfg.get("Handler")==handler and
                cfg.get("Environment",{}).get("Variables",{}).get("STOCKLENS_DATA_BUCKET")==BUCKET,
                "DEPLOYED_LAMBDA_UNVERIFIED:"+fn)
    for key, sha in OLD_PINS.items():
        _,payload,digest = immutable_json(s3,key)
        require(digest==sha and isinstance(payload,dict),
                "OLD_EPOCH_ANCHOR_DRIFT:" + key)
    key="signals/"+prev+".json"
    head,signal,signal_sha=immutable_json(s3,key)
    require(isinstance(signal,dict) and
            signal.get("mode")=="SHADOW_ONLY_NO_BROKER_ACTIONS" and
            signal.get("latest",{}).get("asof_date")==prev and
            signal.get("execution_plan",{}).get("broker_actions_enabled") is False,
            "PREVIOUS_DAY_SIGNAL_NOT_FROZEN_SHADOW")
    saved=utc(head.get("LastModified"))
    require(prev_close <= saved < opening,
            "PREVIOUS_SIGNAL_NOT_SAVED_IN_CORRECT_LAG1_WINDOW")
    book="NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH4_"+first.strftime("%Y%m%d")
    prefix="paper/epochs/"+book+"/"
    # Existing approval can be idempotently reverified by approve(); but
    # inspect never treats an existing book as a fresh unstarted epoch.
    return {"book":book,"prefix":prefix,"first_session":first.isoformat(),
            "prior_session":prev,
            "opening_utc":opening.isoformat(),
            "prior_signal_key":key,"prior_signal_version_id":head["VersionId"],
            "prior_signal_sha256":signal_sha,
            "prior_signal_s3_saved_utc":saved.isoformat(),
            "old_epoch_last_qualified":PRIOR_LAST_QUALIFIED,
            "prod_all_rules_disabled":True,
            "st_old_paper_schedule_remains_disabled":True,
            "broker_actions":False}


def approve(s3, info, now, *, explicit):
    require(explicit is True, "EXPLICIT_NEW_EPOCH_CASH_APPROVAL_REQUIRED")
    opening=datetime.fromisoformat(info["opening_utc"])
    require(utc(now)<opening,"PREOPEN_DEADLINE_PASSED_NO_BACKDATING")
    key=info["prefix"]+"preopen-inception-approval.json"
    # Refuse ANY existing new-epoch history, even with current delete markers.
    version_inventory(s3,info["prefix"])
    record={
        "schema":"stocklens-epoch4-preopen-inception-intent-v1",
        "book":info["book"],"first_session":info["first_session"],
        "prior_signal_key":info["prior_signal_key"],
        "prior_signal_version_id":info["prior_signal_version_id"],
        "prior_signal_sha256":info["prior_signal_sha256"],
        "starting_cash_usd":100000.0,"starting_shares":{"QQQ":0,"TQQQ":0},
        "old_nav_transferred":False,"old_book_last_qualified":PRIOR_LAST_QUALIFIED,
        "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS","broker_orders_authorized":False,
        "genesis_created":False,"paper_trades_created":False}
    raw=json.dumps(record,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
    digest=hashlib.sha256(raw).hexdigest()
    response=s3.put_object(Bucket=BUCKET,Key=key,Body=raw,
                           IfNoneMatch="*",ContentType="application/json",
                           Metadata={"sha256":digest,"kind":"epoch4-approval"})
    version=response.get("VersionId")
    require(version not in (None,"","null"),"APPROVAL_PUT_NOT_VERSIONED")
    head,received,observed_digest=immutable_json(s3,key)
    require(head["VersionId"]==version and observed_digest==digest and
            received==record and
            (head.get("Metadata") or {}).get("sha256")==digest,
            "APPROVAL_READBACK_MISMATCH")
    require(utc(head.get("LastModified"))<opening,
            "S3_SERVER_APPROVAL_AFTER_OPEN_NOT_ELIGIBLE")
    return {"status":"ONE_PREOPEN_INTENT_WRITTEN_NOT_PAPER_RECOVERY",
            "approval_key":key,"approval_sha256":digest,
            "approval_versioned":True,"first_session":info["first_session"],
            "s3_preopen_time_verified":True,"genesis_created":False,
            "paper_trades_created":False,"old_book_modified":False,
            "broker_orders":False,"prod_untouched":True}


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("--first-session",required=True)
    p.add_argument("--approve-new-simulated-cash-100000",action="store_true")
    args=p.parse_args(argv)
    first=date.fromisoformat(args.first_session)
    import boto3
    ses=boto3.session.Session(region_name=REGION)
    clients={k:ses.client(k) for k in
             ("sts","cloudformation","events","lambda","s3")}
    now=datetime.now(timezone.utc)
    info=check(clients,first,now)
    if not args.approve_new_simulated_cash_100000:
        print(json.dumps({"status":"PREOPEN_SIGNAL_AND_OLD_EPOCH_VERIFIED_INSPECT_ONLY",
            "approval_required_for_new_simulated_cash":True,
            "new_paper_runtime_deployed":False,"new_epoch_watchdog_deployed":False,
            "aws_mutations":False,**info},sort_keys=True,indent=2))
        return 0
    result=approve(clients["s3"],info,datetime.now(timezone.utc),explicit=True)
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status":"PREOPEN_EPOCH4_BLOCKED_NO_RECOVERY",
            "reason":str(exc)[:280],"broker_orders":False,
            "prod_untouched":True}))
        raise SystemExit(2)

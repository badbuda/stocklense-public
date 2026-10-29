#!/usr/bin/env python3
"""Prospective FIRST Paper book in the new isolated stocklens-st AWS stack.

status: verify ST-only infrastructure and immutable candidate Signal S3 presence, no invokes.
check: verify real previous/current ST Signals, minute-level observed Yahoo
quotes and frozen model accounting using READ-ONLY dedicated preflight Lambda.
bootstrap --yes: same gate plus explicit CLI approval then exactly ONE modeled Paper
receipt, immutable continuity and genesis, independently checked afterward.
This script NEVER enables schedules, touches PROD, migrates old paper or trades.
"""
from __future__ import annotations
import argparse
from datetime import date, datetime, timezone
import json
import re
from pathlib import Path
import subprocess
import sys
import tempfile

ACCOUNT = "634740393398"
REGION = "eu-central-1"
STACK = "stocklens-st"
PROD = "stocklens-prod"
SOURCE = "stocklens-independent-staging"
BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK"
FIRST_SESSION = "2026-10-30"  # First prospective Paper session after ST Signal activation
CONSENT = "CREATE_PROSPECTIVE_ST_PAPER_ONLY_NO_BROKER"
AUDIT = "PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS"


def aws(service, op, *args):
    p = subprocess.run(
        ["aws", "--region", REGION, "--no-cli-pager", "--output", "json", service, op, *args],
        capture_output=True, text=True, timeout=180, check=False,
    )
    if p.returncode:
        raise RuntimeError("AWS_FAILED:" + service + "/" + op + ":" + p.stderr[:280])
    return json.loads(p.stdout)


def stack(name):
    res = aws("cloudformation", "describe-stacks", "--stack-name", name)
    x = res.get("Stacks", [])
    if len(x)!=1 or x[0]["StackStatus"] not in ("CREATE_COMPLETE","UPDATE_COMPLETE"):
        raise RuntimeError("STACK_NOT_STABLE:" + name)
    return {v["OutputKey"]:v["OutputValue"] for v in x[0].get("Outputs",[])}


def check_rule(outputs, key, expected):
    rule = outputs.get(key)
    if not rule or aws("events","describe-rule","--name",rule).get("State")!=expected:
        raise RuntimeError("UNSAFE_EVENTBRIDGE_STATE:" + key)


def fn_config(name, handler, bucket):
    cfg = aws("lambda","get-function-configuration","--function-name",name)
    if (cfg.get("State")!="Active" or cfg.get("LastUpdateStatus")!="Successful"
        or cfg.get("Handler")!=handler
        or cfg.get("Environment",{}).get("Variables",{}).get("STOCKLENS_DATA_BUCKET")!=bucket):
        raise RuntimeError("WRONG_LAMBDA_HANDLER_OR_BUCKET:" + name)
    return cfg


def preconditions():
    if aws("sts","get-caller-identity").get("Account")!=ACCOUNT:
        raise RuntimeError("WRONG_AWS_ACCOUNT_STOP")
    st,prod,source=stack(STACK),stack(PROD),stack(SOURCE)
    if st.get("CandidateDataBucket")!=BUCKET or prod.get("CandidateDataBucket")==BUCKET:
        raise RuntimeError("ST_PROD_S3_ISOLATION_INVALID")
    for target in (st,prod):
        check_rule(target,"CandidatePaperOnlyRuleName","DISABLED")
        check_rule(target,"CandidateOrchestratorRuleName","DISABLED")
    check_rule(st,"CandidateSignalOnlyRuleName","ENABLED")
    check_rule(prod,"CandidateSignalOnlyRuleName","DISABLED")
    pf_name=st.get("CandidatePaperPreflightFunctionName")
    paper_name=st.get("CandidatePaperFunctionName")
    if pf_name!=STACK+"-paper-preflight" or paper_name!=STACK+"-paper-candidate":
        raise RuntimeError("WRONG_ST_PAPER_FUNCTIONS")
    pf=fn_config(pf_name,"infra.aws.independent_paper.preflight_handler",BUCKET)
    paper=fn_config(paper_name,"infra.aws.independent_paper.handler",BUCKET)
    old_fn=source.get("CandidatePaperFunctionName")
    old=aws("lambda","get-function-configuration","--function-name",old_fn)
    if not pf.get("CodeSha256") or pf["CodeSha256"]!=paper.get("CodeSha256") or pf["CodeSha256"]!=old.get("CodeSha256"):
        raise RuntimeError("UNVERIFIED_DEPLOYED_FROZEN_PAPER_ARTIFACT_SHA")
    role = aws("cloudformation","describe-stack-resource","--stack-name",STACK,
               "--logical-resource-id","CandidatePaperPreflightRole")
    physical=role.get("StackResourceDetail",{}).get("PhysicalResourceId")
    if not physical or pf.get("Role","").split("/")[-1]!=physical:
        raise RuntimeError("READ_ONLY_PREFLIGHT_ROLE_NOT_BOUND")
    topic=st.get("CandidateAlertsTopic")
    if topic!=f"arn:aws:sns:{REGION}:{ACCOUNT}:{STACK}-candidate-alerts":
        raise RuntimeError("WRONG_ST_ALERT_TOPIC")
    subs=aws("sns","list-subscriptions-by-topic","--topic-arn",topic).get("Subscriptions",[])
    if not any(s.get("Protocol")=="email" and s.get("SubscriptionArn") not in (None,"PendingConfirmation") for s in subs):
        raise RuntimeError("ST_SNS_EMAIL_UNCONFIRMED")
    print("ST_PAPER_PREFLIGHT_INFRA_PASS:signal=ENABLED:paper=DISABLED:prod=DISABLED")
    return pf_name,paper_name


def invoke(name,event):
    with tempfile.TemporaryDirectory(prefix="stocklens-st-prospective-") as d:
        req=Path(d)/"request.json"
        out=Path(d)/"response.json"
        req.write_text(json.dumps(event),encoding="utf-8")
        meta=aws("lambda","invoke","--function-name",name,
                 "--cli-binary-format","raw-in-base64-out",
                 "--payload","fileb://"+str(req),str(out))
        try:reply=json.loads(out.read_text(encoding="utf-8"))
        except (OSError,ValueError) as exc:raise RuntimeError("LAMBDA_INVALID_JSON:"+name) from exc
        if meta.get("StatusCode")!=200 or meta.get("FunctionError"):
            raise RuntimeError("LAMBDA_FUNCTION_ERROR:"+name+":"+str(reply)[:600])
        return reply


def validate_preflight(report,session):
    if (report.get("status")!="STAGING_PAPER_BOOTSTRAP_PREFLIGHT_PASS_READ_ONLY"
        or report.get("session")!=session or not isinstance(report.get("prior_session"),str)
        or report.get("prior_session")>=session
        or report.get("market_source")!="YFINANCE_1M_RAW"
        or report.get("paper_accounting_audit")!=AUDIT):
        raise RuntimeError("PAPER_PREFLIGHT_NOT_PASS")
    for name in ("broker_actions","broker_orders","broker_fills","market_data_written",
                 "paper_data_written","genesis_written","prospective_bootstrap_authorized"):
        if report.get(name) is not False:
            raise RuntimeError("PREFLIGHT_UNSAFE_FLAG:"+name)
    for name in ("prior_signal_s3_version_id","current_signal_s3_version_id",
                 "model_candidate_sha256","prior_signal_s3_sha256","current_signal_s3_sha256"):
        if not report.get(name):
            raise RuntimeError("PREFLIGHT_MISSING_SOURCE_PROOF:"+name)
    if not re.fullmatch(r"[0-9a-f]{64}",report["model_candidate_sha256"]):
        raise RuntimeError("PREFLIGHT_MODEL_HASH_INVALID")
    print("ST_PAPER_PROSPECTIVE_READ_ONLY_PASS:"+session+
          ":prior="+report["prior_session"]+":modeled_trades="+str(report["paper_model_trades"])+
          ":modeled_equity="+str(report["paper_model_equity"]))


def bootstrap(paper_fn,session):
    result=invoke(paper_fn,{
        "mode":"STAGING_PAPER_ONLY",
        "expected_session":session,
        "bootstrap":True,
    })
    if (result.get("status")!="STAGED_PAPER_VERIFIED"
        or result.get("session")!=session or result.get("book")!=BOOK
        or result.get("audit")!=AUDIT
        or result.get("broker_orders") is not False
        or result.get("broker_fills") is not False
        or not result.get("paper_version_id")
        or not re.fullmatch("[0-9a-f]{64}",str(result.get("paper_sha256")))):
        raise RuntimeError("PAPER_MUTATION_RETURN_UNVERIFIED_REVIEW_PARTIAL_STATE_NO_BLIND_RETRY")
    first = result
    try:
        result=invoke(paper_fn,{
            "mode":"STAGING_PAPER_SCHEDULE_READINESS",
            "expected_session":session,
            "bootstrap":False,
        })
    except Exception:
        raise RuntimeError("PAPER_GENESIS_COMMITTED_BUT_VERIFY_FAILED_REVIEW_S3_NO_BLIND_RETRY")
    if (result.get("status")!="STAGING_PAPER_SCHEDULE_READINESS_PASS_READ_ONLY"
        or result.get("session")!=session
        or result.get("genesis_session")!=session
        or result.get("chain_sessions")!=1
        or result.get("paper_sha256")!=first.get("paper_sha256")
        or result.get("paper_version_id")!=first.get("paper_version_id")
        or result.get("continuity_status") not in ("ON_TIME_QUALIFIED","LATE_WITH_CONTEMPORANEOUS_EVIDENCE")
        or result.get("broker_actions") is not False
        or result.get("paper_data_written") is not False
        or result.get("paper_automation_authorized") is not False):
        raise RuntimeError("ST_PAPER_BOOTSTRAP_CHAIN_UNVERIFIED_REVIEW_PARTIAL_S3")
    print("ST_FIRST_PAPER_GENESIS_CHAIN_PASS:"+session+
          ":continuity="+str(result.get("continuity_status"))+
          ":sha="+str(result.get("paper_sha256")))
    print("ST_PAPER_SCHEDULE_REMAINS_DISABLED:NO_BROKER_NO_PROD")


def safe_head(bucket, key):
    """Read-only S3 presence. 404 is missing; IAM/other errors fail closed."""
    p=subprocess.run(["aws","--region",REGION,"--no-cli-pager","--output","json",
                      "s3api","head-object","--bucket",bucket,"--key",key],
                     capture_output=True,text=True,timeout=30,check=False)
    if p.returncode:
        err=p.stderr
        if "404" in err or "NoSuchKey" in err or "Not Found" in err:
            return None
        raise RuntimeError("ST_S3_HEAD_FAILED:"+key+":"+err[:220])
    meta=json.loads(p.stdout)
    if not meta.get("VersionId") or meta["VersionId"]=="null" or not meta.get("LastModified"):
        raise RuntimeError("ST_UNVERSIONED_OR_UNTIMED_S3_OBJECT:"+key)
    return meta


def status(session):
    """No Lambda invocation, no writable AWS calls, no fabricated records."""
    # This already enforces account isolation, disabled Paper+PROD schedules,
    # frozen function SHA, role provenance and confirmed ST alarm delivery.
    preconditions()
    # The first authorized session is explicitly the Oct 30 completed session.
    # Other dates use a market calendar, not a weekend subtraction.
    if session==FIRST_SESSION:
        prior="2026-10-29"
    else:
        try:
            import exchange_calendars as xcals
            cal=xcals.get_calendar("XNYS")
            if not cal.is_session(session):
                raise RuntimeError("NOT_XNYS_SESSION:"+session)
            prior=cal.previous_session(session).date().isoformat()
        except ImportError as exc:
            raise RuntimeError("CALENDAR_REQUIRED_FOR_CUSTOM_SESSION") from exc
    keys=[f"signals/{prior}.json",f"signals/{session}.json"]
    present=[safe_head(BUCKET,key) is not None for key in keys]
    genesis=safe_head(BUCKET,f"paper/book/{BOOK}/genesis.json")
    print("ST_PAPER_PROSPECTIVE_STATUS:"+session+
          ":PRIOR_SIGNAL="+("PRESENT" if present[0] else "MISSING")+
          ":CURRENT_SIGNAL="+("PRESENT" if present[1] else "MISSING")+
          ":GENESIS="+("PRESENT" if genesis is not None else "ABSENT"))
    if genesis is not None:
        print("ST_PAPER_BOOK_ALREADY_EXISTS:NO_BOOTSTRAP_REVIEW_CONTINUITY_AND_SCHEDULE")
    elif all(present):
        print("ST_PAPER_SIGNALS_PRESENT:RUN_check_FOR_FULL_READ_ONLY_ACCOUNTING_PREFLIGHT")
    else:
        print("ST_PAPER_WAITING_FOR_TWO_VERSIONED_SIGNALS:NO_WRITES")
    print("ST_PAPER_AND_PROD_SCHEDULES_REMAIN_DISABLED")


def main():
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("status","check","bootstrap"))
    p.add_argument("--session",default=FIRST_SESSION,
                   help="Prospective XNYS Paper execution day, default 2026-10-30")
    p.add_argument("--yes",action="store_true",
                   help="Explicitly authorize exactly one modeled ST Paper genesis, never schedules or brokerage")
    p.add_argument("--confirm",default="",help=argparse.SUPPRESS)
    args=p.parse_args()
    if date.fromisoformat(args.session).isoformat()!=args.session:
        raise RuntimeError("BAD_SESSION_FORMAT")
    if args.mode in ("status","check") and (args.yes or args.confirm):
        raise RuntimeError("READ_ONLY_MODE_MUST_NOT_APPROVE_MUTATION")
    if args.mode=="bootstrap":
        if args.confirm and args.confirm!=CONSENT:
            raise RuntimeError("INVALID_BOOTSTRAP_CONFIRMATION")
        if not (args.yes or args.confirm==CONSENT):
            raise RuntimeError("EXPLICIT_ST_ONLY_BOOTSTRAP_--yes_REQUIRED")
    if args.mode=="status":
        status(args.session)
        return
    pf,paper=preconditions()
    reply=invoke(pf,{"mode":"STAGING_PAPER_BOOTSTRAP_PREFLIGHT",
                     "expected_session":args.session,"bootstrap":False})
    validate_preflight(reply,args.session)
    if args.mode=="check":
        print("READ_ONLY_FIRST_ST_PAPER_CHECK_PASS:NO_PAPER_CREATED")
        return
    # Mutation requires explicit operator-selected bootstrap --yes, still
    # protected by every read-only AWS and observed Yahoo accounting check.
    bootstrap(paper,args.session)


if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("ST_PROSPECTIVE_PAPER_BLOCKED:"+str(exc))
        sys.exit(2)

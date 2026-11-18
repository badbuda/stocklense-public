#!/usr/bin/env python3
"""SL-56: opt-in ST Paper legacy retry containment, with original alarms retained.

Stops the *old* failing Paper EventBridge rule only after pinned production
disarm, immutable old-book gap checks and observed incident traceback.
This is a maintenance PAUSE, NOT Paper recovery or a green monitor. Distinct
future epoch automation has not been configured by this script.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import sys

from infra.aws import sl56_epoch3_readonly_preflight as check

PAPER_LAMBDA_CODE_SHA_B64="YKpLN8Ks36blX4J9z+GnDKx9fCN87tA7wwc5Sc/25WQ="
PAPER_CRON="cron(0 13 ? * TUE-SAT *)"
ERROR_CODE="TOO_FEW_MINUTE_BARS:QQQ:2026-11-05:289:required=385"


def require(ok,code):
    check.require(ok,code)


def readiness(c):
    # Full read-only S3 gap, old anchor, signed Signal and PROD isolation gates.
    result=check.preflight(c)
    cf, ev, lam, logs=(c[k] for k in ("cloudformation","events","lambda","logs"))
    st=check.stack_outputs(cf,check.ST)
    fn=st["CandidatePaperFunctionName"]
    require(fn=="stocklens-st-paper-candidate", "UNEXPECTED_ST_PAPER_FUNCTION")
    cfg=lam.get_function_configuration(FunctionName=fn)
    require(cfg["CodeSha256"]==PAPER_LAMBDA_CODE_SHA_B64 and
            cfg["State"]=="Active" and
            cfg["LastUpdateStatus"]=="Successful",
            "ST_PAPER_CODE_CHANGED_STOP")
    rulename=st["CandidatePaperOnlyRuleName"]
    rule=ev.describe_rule(Name=rulename)
    require(rule["State"]=="ENABLED" and
            rule["ScheduleExpression"]==PAPER_CRON,
            "ST_PAPER_RULE_DRIFT_OR_NOT_ENABLED")
    targets=ev.list_targets_by_rule(Rule=rulename).get("Targets",[])
    require(len(targets)==1 and targets[0].get("Arn")==cfg.get("FunctionArn"),
            "ST_PAPER_RULE_TARGET_MISMATCH")
    a=datetime(2026,11,11,12,55,tzinfo=timezone.utc)
    b=datetime(2026,11,11,13,15,tzinfo=timezone.utc)
    events=logs.filter_log_events(
        logGroupName=f"/aws/lambda/{fn}",startTime=int(a.timestamp()*1000),
        endTime=int(b.timestamp()*1000),limit=500).get("events",[])
    require(any(ERROR_CODE in event.get("message","") for event in events),
            "NOV11_INCIDENT_NOT_VERIFIED_FROM_CLOUDWATCH")
    return {
        "status":"ST_OLD_PAPER_RETRY_CONTAINMENT_PREFLIGHT_PASS",
        "rule_name":rulename,
        "paper_function":fn,
        "failure_signature_proven":ERROR_CODE,
        "old_book_gaps":result["old_book_gaps_still_absent"],
        "new_epoch_running":False,
        "paper_trading_operational":False,
        "old_alarm_history_preserved":True,
        "watchdog_not_disabled":True,
        "production_schedules_disabled":True,
        "broker_orders":False,
    }


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("inspect","pause"))
    p.add_argument("--approve-st-paper-pause",action="store_true")
    args=p.parse_args(argv)
    if args.mode=="pause":
        require(args.approve_st_paper_pause,
                "EXPLICIT_APPROVAL_REQUIRED_TO_PAUSE_ST_PAPER_RULE")
    else:
        require(not args.approve_st_paper_pause,"INSPECT_MUST_NOT_APPROVE")
    import boto3
    session=boto3.Session(region_name=check.REGION)
    c={name:session.client(name) for name in
       ("sts","cloudformation","events","lambda","s3","logs")}
    result=readiness(c)
    result["mode"]=args.mode
    print(json.dumps(result,sort_keys=True),flush=True)
    if args.mode=="inspect":
        return 0
    # No S3, CloudWatch, Lambda or PROD mutation; one ST event rule only.
    c["events"].disable_rule(Name=result["rule_name"])
    state=c["events"].describe_rule(Name=result["rule_name"])
    require(state.get("State")=="DISABLED","ST_PAPER_PAUSE_UNVERIFIED")
    print(json.dumps({
        "status":"ST_OLD_PAPER_SCHEDULE_PAUSED_GAP_STILL_OPEN",
        "old_paper_schedule_disabled":True,
        "new_paper_epoch_not_running":True,
        "old_history_and_alarms_preserved":True,
        "watchdog_unchanged":True,
        "production_untouched":True,
        "cloudformation_st_drift_requires_reconciliation":True,
        "broker_orders":False,
    },sort_keys=True))
    return 0


if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(json.dumps({
            "status":"ST_OLD_PAPER_PAUSE_BLOCKED_OR_PARTIAL_REVIEW_REQUIRED",
            "reason":str(exc)[:240],
            "prod_not_mutated":True,
        }),file=sys.stderr)
        sys.exit(2)

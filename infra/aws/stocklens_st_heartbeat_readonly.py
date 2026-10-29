#!/usr/bin/env python3
"""Read-only acceptance of ST watchdog heartbeat after isolated metric filter deployment.

The AWS CloudWatch Logs filter does not backfill existing messages. This
diagnostic distinguishes a fresh hourly Lambda REPORT from a fresh isolated
CloudWatch metric and from alarm recovery. Does not invoke Lambda, update
alerts, write S3, create fills, or touch PROD.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timedelta,timezone
import json
import sys

ACCOUNT="634740393398"
REGION="eu-central-1"
STACK="stocklens-st"
LOG_ID="CandidateSessionWatchdogLogs"
RULE_ID="CandidateSessionWatchdogSchedule"
ALARM_ID="WatchdogHeartbeatDeadmanAlarm"
LOG_METRIC_NAMESPACE="StockLens/IsolatedST"
METRIC="WatchdogHeartbeat"
FILTER_NAME=STACK+"-watchdog-"+METRIC
EXPECTED_FNC=STACK+"-session-watchdog"
EXPECTED_LOG="/aws/lambda/"+EXPECTED_FNC


def require(condition, message):
    if not condition: raise RuntimeError(message)


def utc(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc)


def physical(cf,logical):
    return cf.describe_stack_resource(StackName=STACK,LogicalResourceId=logical)[
        "StackResourceDetail"]["PhysicalResourceId"]


def scan_watchdog(logs,log_name,now):
    """Page JSON-only app messages. Never treat truncated scans as conclusive."""
    events=[]
    seen=set()
    token=None
    end_ms=int(now.timestamp()*1000)
    # Include a 6-hour look-back, because watchdog emits only hourly.
    start_ms=int((now-timedelta(hours=6)).timestamp()*1000)
    truncated=False
    for page in range(12):
        kwargs={"logGroupName":log_name,"startTime":start_ms,"endTime":end_ms,
                "filterPattern":"{ $.metrics.WatchdogHeartbeat = * }","limit":100}
        if token: kwargs["nextToken"]=token
        result=logs.filter_log_events(**kwargs)
        for e in result.get("events",[]):
            eid=e.get("eventId")
            if eid in seen and eid is not None: continue
            if eid is not None: seen.add(eid)
            try: data=json.loads(e["message"].strip())
            except (ValueError,KeyError,TypeError): continue
            if not isinstance(data,dict) or not isinstance(data.get("metrics"),dict):
                continue
            hb=data["metrics"].get(METRIC)
            if type(hb) not in (int,float): continue
            events.append({"utc":utc(e["timestamp"]).isoformat(),
                           "timestamp_ms":e["timestamp"],
                           "heartbeat":hb,"watchdog_status":data.get("status"),
                           "failures":data.get("failures",[])[:5]})
        next_token=result.get("nextToken")
        if not next_token or next_token==token: break
        if page==11: truncated=True
        token=next_token
    events.sort(key=lambda e:e["timestamp_ms"])
    return {"events":events,"truncated":truncated}


def inspect(clients, now=None):
    now=now or datetime.now(timezone.utc)
    require(now.tzinfo is not None,"NAIVE_TIME")
    now=now.astimezone(timezone.utc)
    sts=clients["sts"]
    require(sts.get_caller_identity()["Account"]==ACCOUNT,"WRONG_ACCOUNT")
    cf,ev,lam,logs,cw=(clients[x] for x in (
        "cloudformation","events","lambda","logs","cloudwatch"))
    stack=cf.describe_stacks(StackName=STACK)["Stacks"][0]
    require(stack.get("StackStatus") in ("CREATE_COMPLETE","UPDATE_COMPLETE"),
            "ST_STACK_NOT_STABLE")
    o={x["OutputKey"]:x["OutputValue"] for x in stack.get("Outputs",[])}
    require(o.get("CandidateSessionWatchdogFunctionName")==EXPECTED_FNC,
            "UNEXPECTED_ST_WATCHDOG_FUNCTION")
    for key in ("CandidatePaperOnlyRuleName","CandidateOrchestratorRuleName"):
        require(ev.describe_rule(Name=o[key]).get("State")=="DISABLED",
                "ST_PAPER_OR_ORCHESTRATOR_ACTIVE")
    require(ev.describe_rule(Name=o["CandidateSignalOnlyRuleName"]).get("State")=="ENABLED",
            "ST_SIGNAL_NOT_ENABLED")
    log_name=physical(cf,LOG_ID)
    require(log_name==EXPECTED_LOG,"UNEXPECTED_ST_WATCHDOG_LOG_GROUP")
    rule_name=physical(cf,RULE_ID)
    rule=ev.describe_rule(Name=rule_name)
    require(rule.get("State")=="ENABLED" and
            rule.get("ScheduleExpression")=="rate(1 hour)",
            "ST_WATCHDOG_RULE_NOT_HOURLY_ENABLED")
    config=lam.get_function_configuration(FunctionName=EXPECTED_FNC)
    require(config.get("State")=="Active" and
            config.get("LastUpdateStatus")=="Successful",
            "ST_WATCHDOG_LAMBDA_UNHEALTHY")
    targets=ev.list_targets_by_rule(Rule=rule_name).get("Targets",[])
    require(len(targets)==1 and targets[0].get("Arn")==config.get("FunctionArn"),
            "ST_WATCHDOG_EVENTBRIDGE_TARGET_MISMATCH")
    filters=logs.describe_metric_filters(logGroupName=log_name,
                                          filterNamePrefix=FILTER_NAME).get("metricFilters",[])
    require(len(filters)==1 and filters[0].get("filterName")==FILTER_NAME,
            "ST_HEARTBEAT_FILTER_NOT_FOUND")
    flt=filters[0]
    pattern="{ $.metrics.WatchdogHeartbeat = * }"
    require(flt.get("filterPattern")==pattern and
            flt.get("logGroupName")==log_name and
            flt.get("metricTransformations")==[{
                "metricName":METRIC,"metricNamespace":LOG_METRIC_NAMESPACE,
                "metricValue":"$.metrics."+METRIC}],
            "ST_HEARTBEAT_FILTER_MISCONFIGURED")
    filter_created=utc(flt["creationTime"])
    alarm_name=physical(cf,ALARM_ID)
    alarm_list=cw.describe_alarms(AlarmNames=[alarm_name]).get("MetricAlarms",[])
    require(len(alarm_list)==1,"HEARTBEAT_ALARM_MISSING")
    alarm=alarm_list[0]
    require(alarm.get("Namespace")==LOG_METRIC_NAMESPACE and
            alarm.get("MetricName")==METRIC and
            alarm.get("TreatMissingData")=="breaching" and
            alarm.get("Period")==3600 and
            alarm.get("EvaluationPeriods")==3 and
            alarm.get("ActionsEnabled") is True,
            "HEARTBEAT_ALARM_CONFIGURATION_CHANGED")
    logscan=scan_watchdog(logs,log_name,now)
    reported=logscan["events"]
    post_filter=[x for x in reported if utc(x["timestamp_ms"])>=filter_created]
    points=cw.get_metric_statistics(
        Namespace=LOG_METRIC_NAMESPACE,MetricName=METRIC,
        StartTime=now-timedelta(hours=6),EndTime=now,
        Period=3600,Statistics=["SampleCount","Maximum"]).get("Datapoints",[])
    points=sorted(points,key=lambda x:x["Timestamp"])
    latest=reported[-1] if reported else None
    latest_post=post_filter[-1] if post_filter else None
    recent_points=[{"utc":x["Timestamp"].isoformat(),
                    "samples":x["SampleCount"],"max":x.get("Maximum")}
                   for x in points[-6:]]
    age=None if latest_post is None else round(
        (now-utc(latest_post["timestamp_ms"])).total_seconds()/60,1)
    if logscan["truncated"]:
        verdict="INCOMPLETE_PAGINATED_WATCHDOG_LOGS"
    elif points and latest_post and
            age is not None and age<=100 and alarm["StateValue"]=="OK":
        verdict="HEARTBEAT_LIVE_AND_ALARM_OK"
    elif not latest_post and now < filter_created+timedelta(minutes=85):
        verdict="AWAITING_FIRST_POST_FILTER_HOURLY_WATCHDOG"
    elif not latest_post:
        verdict="WATCHDOG_POST_FILTER_LOG_MISSING_INVESTIGATE"
    elif not points and age is not None and age<=25:
        verdict="LOG_PRESENT_METRIC_PUBLICATION_PENDING"
    elif not points:
        verdict="LOG_PRESENT_BUT_ISOLATED_METRIC_MISSING_INVESTIGATE"
    elif age is not None and age>100:
        verdict="WATCHDOG_REPORT_STALE_INVESTIGATE"
    elif alarm["StateValue"]=="ALARM":
        verdict="HEARTBEAT_REPORTED_ALARM_STILL_EVALUATING"
    else:
        verdict="HEARTBEAT_REPORTED_REVIEW_ALARM"
    return {
        "checked_utc":now.isoformat(),"verdict":verdict,
        "st_cloudformation":"STABLE",
        "st_signal_rule":"ENABLED",
        "st_paper_orchestrator":"DISABLED",
        "watchdog_rule":"ENABLED_HOURLY_TARGET_VERIFIED",
        "metric_filter_created_utc":filter_created.isoformat(),
        "metric_filter":"VERIFIED_ST_ONLY",
        "watchdog_reports_last_6h":len(reported),
        "watchdog_logs_truncated":logscan["truncated"],
        "last_watchdog_report":latest,
        "last_post_filter_report":latest_post,
        "age_last_post_filter_report_minutes":age,
        "isolated_metric_datapoints_last_6h":recent_points,
        "heartbeat_alarm_state":alarm["StateValue"],
        "heartbeat_alarm_reason":alarm.get("StateReason","")[:300],
        "no_aws_mutations":True,"broker_actions":False
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--json",action="store_true")
    args=p.parse_args()
    import boto3
    session=boto3.session.Session(region_name=REGION)
    clients={name:session.client(name) for name in (
        "sts","cloudformation","events","lambda","logs","cloudwatch")}
    try:
        output=inspect(clients)
    except Exception as exc:
        output={"verdict":"READ_ONLY_DIAGNOSTIC_BLOCKED",
                "reason":str(exc)[:350],"no_aws_mutations":True}
    if args.json:
        print(json.dumps(output,indent=2,ensure_ascii=False,default=str))
    else:
        print("ST_WATCHDOG_HEARTBEAT:",output["verdict"])
        if "reason" in output: print("REASON:",output["reason"])
        else:
            print("FILTER_CREATED:",output["metric_filter_created_utc"])
            print("LOGS_LAST_6H:",output["watchdog_reports_last_6h"],
                  "TRUNCATED:",output["watchdog_logs_truncated"])
            print("LAST_REPORT:",output["last_watchdog_report"])
            print("FIRST_POST_FILTER:",output["last_post_filter_report"])
            print("ISOLATED_METRICS:",output["isolated_metric_datapoints_last_6h"])
            print("ALARM:",output["heartbeat_alarm_state"],
                  output["heartbeat_alarm_reason"])
        print("NO_AWS_MUTATIONS_NO_BROKER")
    return 2 if output["verdict"]=="READ_ONLY_DIAGNOSTIC_BLOCKED" else 0


if __name__=="__main__":
    sys.exit(main())

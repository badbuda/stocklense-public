#!/usr/bin/env python3
"""ST-only AWS Watchdog/CloudWatch alarm forensics; read-only.

Show the *recorded reason*, actual CloudWatch datapoints, last state
transitions and recent structured watchdog reports, without resetting alarm
states or introducing a fake Paper receipt. Existing configured CloudWatch
alarms remain unmodified. Prints no secrets or raw S3 private data.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
import json
import sys

ACCOUNT="634740393398"
REGION="eu-central-1"
ST="stocklens-st"
ST_BUCKET="stocklens-st-candidatedata-6jj7i9fxjmfr"
PROD="stocklens-prod"
ALARMS=(
    "MissingOrLateScheduledSignalsAlarm",
    "MissedSessionsAlarm",
    "WatchdogFailClosedAlarm",
    "WatchdogConfigurationErrorAlarm",
    "WatchdogHeartbeatDeadmanAlarm",
    "CandidateSessionWatchdogErrorsAlarm",
    "CandidatePaperErrorsAlarm",
)


def require(ok, message):
    if not ok: raise RuntimeError(message)


def stack_outputs(cf, name):
    result=cf.describe_stacks(StackName=name).get("Stacks",[])
    require(len(result)==1 and result[0]["StackStatus"] in ("CREATE_COMPLETE","UPDATE_COMPLETE"),"STACK_NOT_STABLE:"+name)
    return {x["OutputKey"]:x["OutputValue"] for x in result[0].get("Outputs",[])}


def alarm_details(cf,cw,logical,*,now):
    physical=cf.describe_stack_resource(StackName=ST,LogicalResourceId=logical)["StackResourceDetail"]["PhysicalResourceId"]
    alarms=cw.describe_alarms(AlarmNames=[physical]).get("MetricAlarms",[])
    require(len(alarms)==1, "ALARM_NOT_FOUND:"+logical)
    a=alarms[0]
    history=cw.describe_alarm_history(
        AlarmName=physical,
        HistoryItemType="StateUpdate",
        StartDate=now-timedelta(hours=18),
        EndDate=now,
        MaxRecords=8
    ).get("AlarmHistoryItems",[])
    metric=None
    if a.get("Namespace") and a.get("MetricName"):
        points=cw.get_metric_statistics(
            Namespace=a["Namespace"],MetricName=a["MetricName"],
            Dimensions=a.get("Dimensions",[]),
            StartTime=now-timedelta(hours=9),EndTime=now,
            Period=int(a.get("Period",3600)),Statistics=["Maximum","SampleCount"]
        ).get("Datapoints",[])
        metric=[{"time":v["Timestamp"].isoformat(),
                 "max":v.get("Maximum"),
                 "samples":v.get("SampleCount")}
                for v in sorted(points,key=lambda x:x["Timestamp"])[-9:]]
    return {
        "name":logical,
        "state":a.get("StateValue"),
        "namespace":a.get("Namespace"),
        "metric_name":a.get("MetricName"),
        "dimensions":a.get("Dimensions",[]),
        "reason":str(a.get("StateReason",""))[:700],
        "reason_data":str(a.get("StateReasonData",""))[:700],
        "state_updated_utc":a["StateUpdatedTimestamp"].isoformat()
            if a.get("StateUpdatedTimestamp") else None,
        "actions_enabled":a.get("ActionsEnabled"),
        "latest_metrics":metric,
        "last_state_updates":[{
            "at":x["Timestamp"].isoformat(),
            "summary":str(x.get("HistorySummary",""))[:380],
            "detail":str(x.get("HistoryData",""))[:700]
        } for x in history[-8:]]
    }


def _watchdog_logs_window(client,fn,now,hours):
    # Read up to eight pages; disclose any truncation rather than hiding errors.
    # The structured JSON printed by the watchdog is more useful than Lambda
    # START/REPORT lines. Search a full day to distinguish older metrics from
    # the latest post-activation report.
    records=[]
    pages=0
    seen=set()
    token=None
    last_next=None
    while pages<8:
        args=dict(logGroupName="/aws/lambda/"+fn,
                  startTime=int((now-timedelta(hours=hours)).timestamp()*1000),
                  endTime=int(now.timestamp()*1000),limit=200)
        if token: args["nextToken"]=token
        response=client.filter_log_events(**args)
        pages+=1
        for evt in response.get("events",[]):
            if evt.get("eventId") in seen and evt.get("eventId") is not None: continue
            if evt.get("eventId") is not None: seen.add(evt["eventId"])
            line=str(evt.get("message","")).strip()
            if not line.startswith("{"): continue
            try: obj=json.loads(line)
            except ValueError: continue
            if not isinstance(obj,dict) or "metrics" not in obj or "failures" not in obj:
                continue
            records.append({
                "utc":datetime.fromtimestamp(evt["timestamp"]/1000,timezone.utc).isoformat(),
                "status":obj.get("status"),
                "mode":obj.get("mode"),
                "failures":obj.get("failures",[])[:25],
                "metrics":obj.get("metrics"),
                "signal_missing":obj.get("missing_scheduled_signals"),
                "paper_missing":obj.get("missed_sessions"),
                "latest_due_signal":obj.get("latest_due_signal_session"),
                "latest_due_status":obj.get("latest_due_signal_status")
            })
        last_next=response.get("nextToken")
        if not last_next or last_next==token: break
        token=last_next
    return {
        "window_hours":hours,
        "last_reports":records[-8:],
        "reports_seen":len(records),
        "pages":pages,
        "pagination_incomplete":pages>=8 and bool(last_next),
        "note":"Log window is bounded; no reports does NOT imply watchdog healthy."
    }



def watchdog_logs(client,fn,now):
    """Never mistake the oldest page of a truncated day for the latest status."""
    for hours in (24,6,2,1):
        result=_watchdog_logs_window(client,fn,now,hours)
        if not result["pagination_incomplete"]:
            result["latest_structured_utc"]=(result["last_reports"][-1]["utc"]
                                             if result["last_reports"] else None)
            return result
    return {"last_reports":[],"reports_seen":None,"pages":8,"window_hours":1,
            "latest_structured_utc":None,"pagination_incomplete":True,
            "note":"INCOMPLETE_EVEN_LAST_HOUR_NO_LATEST_STATE_CLAIM"}


def isolated_metric_origins(logs,watchdog_name):
    """Check ST metric filters are scoped to ST's own CloudWatch log group."""
    group="/aws/lambda/"+watchdog_name
    expected={"MissedSessions","WatchdogFailClosed","WatchdogHeartbeat",
              "MissingOrLateScheduledSignals","BookHalted","SchedulerStateMismatch",
              "InvalidReceipts","ConfigurationError"}
    try:
        rows=logs.describe_metric_filters(
            logGroupName=group,filterNamePrefix="stocklens-st-watchdog-"
        ).get("metricFilters",[])
    except Exception as exc:
        return {"status":"UNVERIFIED_METRIC_FILTER_READ","error_type":type(exc).__name__}
    matched=set()
    for row in rows:
        tt=row.get("metricTransformations",[])
        if row.get("logGroupName")!=group or len(tt)!=1:continue
        t=tt[0];name=t.get("metricName")
        if (name in expected and t.get("metricNamespace")=="StockLens/IsolatedST"
            and t.get("metricValue")=="$.metrics."+name
            and row.get("filterPattern")=="{ $.metrics."+name+" = * }"):
            matched.add(name)
    return {"status":"ISOLATED_ST_FILTERS_VERIFIED" if matched==expected
                     else "ST_ISOLATION_INCOMPLETE_OR_UNVERIFIED",
            "matched":len(matched),"expected":len(expected),"log_group":group,
            "note":"Metric origin verification does not prove Paper receipts."}


def summarize(evidence):
    print("ST_ALARM_FORENSICS:READ_ONLY")
    print("MONITORING_PARAMETERS:",evidence.get("st_monitoring_parameters"))
    print("ST_SCHEDULES:", evidence.get("st_schedules"))
    print("ISOLATED_METRIC_ORIGINS:",evidence.get("isolated_metric_origins"))
    print("SHARED_METRIC_RISK:",evidence["shared_metric_risk"]["status"],
          ",".join(evidence["shared_metric_risk"]["unscoped_alarm_names"]))
    for logical,data in evidence["alarms"].items():
        print("ALARM:",logical,data.get("state",data.get("status")),
              "updated="+str(data.get("state_updated_utc")),
              "namespace="+str(data.get("namespace")),
              "reason="+str(data.get("reason",data.get("message","")))[:350])
        if data.get("state")=="ALARM":
            print("  recent_metric_points:",data.get("latest_metrics",[])[-3:])
            print("  state_change:",data.get("last_state_updates",[])[-1:])
    for name,data in evidence.get("watchdogs_by_environment",{}).items():
        print("WATCHDOG:",name,"reports_seen="+str(data.get("reports_seen")),
              "truncated="+str(data.get("pagination_incomplete")),
              "window_hours="+str(data.get("window_hours")),
              "latest_report_utc="+str(data.get("latest_structured_utc")),
              "error="+str(data.get("message","")))
        for report in data.get("last_reports",[])[-2:]:
            print("  ",report["utc"],report.get("status"),
                  "failures="+str(report.get("failures",[]))[:650],
                  "metrics="+str(report.get("metrics",{}))[:500])
    print("NO_AWS_MUTATIONS_NO_BROKER_NO_PAPER")


def main():
    import argparse
    p=argparse.ArgumentParser()
    p.add_argument("--summary",action="store_true")
    p.add_argument("--output")
    args=p.parse_args()
    import boto3
    now=datetime.now(timezone.utc)
    session=boto3.session.Session(region_name=REGION)
    sts=session.client("sts")
    require(sts.get_caller_identity()["Account"]==ACCOUNT,"WRONG_AWS_ACCOUNT")
    cf=session.client("cloudformation")
    st=stack_outputs(cf,ST)
    prod=stack_outputs(cf,PROD)
    old=stack_outputs(cf,"stocklens-independent-staging")
    require(st.get("CandidateDataBucket")==ST_BUCKET and
            prod.get("CandidateDataBucket")!=ST_BUCKET,
            "UNEXPECTED_ST_OR_PROD_BUCKET")
    events=session.client("events")
    # ST Paper is allowed to be ENABLED in the guarded recurring-Paper phase.
    # Capture its *actual* state instead of aborting forensics or claiming it is disabled.
    st_schedules={}
    for name in ("CandidateSignalOnlyRuleName","CandidatePaperOnlyRuleName",
                 "CandidateOrchestratorRuleName"):
        state=events.describe_rule(Name=st[name]).get("State")
        require(state in ("ENABLED","DISABLED"), "ST_RULE_STATE_UNKNOWN:"+name)
        st_schedules[name]=state
    require(st_schedules["CandidateOrchestratorRuleName"]=="DISABLED",
            "UNSAFE_ST_ORCHESTRATOR_RULE")
    for name in ("CandidatePaperOnlyRuleName","CandidateOrchestratorRuleName",
                 "CandidateSignalOnlyRuleName"):
        require(events.describe_rule(Name=prod[name])["State"]=="DISABLED",
                "UNSAFE_PROD_RULE")
    cw=session.client("cloudwatch")
    logs=session.client("logs")
    stack_params=cf.describe_stacks(StackName=ST)["Stacks"][0].get("Parameters",[])
    selected={x["ParameterKey"]:x.get("ParameterValue","")
              for x in stack_params if x["ParameterKey"] in (
                  "MonitoringStartSession","ExpectedSchedulerState",
                  "CandidateSignalScheduleState")}
    evidence={
        "kind":"STOCKLENS_ST_ALARM_READ_ONLY_FORENSICS",
        "st_monitoring_parameters":selected,
        "checked_utc":now.isoformat(),
        "account":ACCOUNT,
        "st_paper":st_schedules["CandidatePaperOnlyRuleName"],
        "st_schedules":st_schedules,
        "prod":"ALL_DISABLED",
        "alarms":{},
        "watchdogs_by_environment":{},
        "aws_mutations":False,
        "broker_orders":False
    }
    for logical in ALARMS:
        try:
            evidence["alarms"][logical]=alarm_details(cf,cw,logical,now=now)
        except Exception as exc:
            evidence["alarms"][logical]={"status":"READ_ERROR","type":type(exc).__name__,
                                         "message":str(exc)[:220]}
    evidence["isolated_metric_origins"]=isolated_metric_origins(
        logs,st["CandidateSessionWatchdogFunctionName"])
    unscoped=[
        logical for logical,item in evidence["alarms"].items()
        if item.get("namespace")=="StockLens/IndependentStaging"
        and not item.get("dimensions") and item.get("metric_name")
    ]
    evidence["shared_metric_risk"]={
        "status":"POTENTIAL_CROSS_ENVIRONMENT_CONTAMINATION" if unscoped
                 else "NO_UNSCOPED_ST_CUSTOM_METRICS_FOUND",
        "unscoped_alarm_names":unscoped,
        "note":"Shared namespace + no Dimensions means per-stack attribution is impossible from alarm datapoints alone."
    }
    for label,stack in (("ST",st),("PROD",prod),("OLD_STAGING",old)):
        try:
            evidence["watchdogs_by_environment"][label]=watchdog_logs(
                logs,stack["CandidateSessionWatchdogFunctionName"],now)
        except Exception as exc:
            evidence["watchdogs_by_environment"][label]={
                "status":"LOGS_UNREADABLE",
                "error_type":type(exc).__name__,
                "message":str(exc)[:220]}
    rendered=json.dumps(evidence,ensure_ascii=False,indent=2,sort_keys=True,default=str)
    if args.output:
        with open(args.output,"w",encoding="utf-8") as file:
            file.write(rendered+"\n")
    if args.summary: summarize(evidence)
    else: print(rendered)
    return 0


if __name__=="__main__":
    try: sys.exit(main())
    except Exception as exc:
        print(json.dumps({"state":"BLOCKED","reason":str(exc)[:320],
                          "aws_mutations":False,"broker_orders":False}))
        sys.exit(2)

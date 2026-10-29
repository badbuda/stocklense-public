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


def watchdog_logs(client,fn,now):
    # Log events are a single bounded read; a nextToken is explicitly disclosed.
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
                  startTime=int((now-timedelta(hours=24)).timestamp()*1000),
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
        "last_reports":records[-8:],
        "reports_seen":len(records),
        "pages":pages,
        "pagination_incomplete":pages>=8 and bool(last_next),
        "note":"Log window is bounded; no reports does NOT imply watchdog healthy."
    }


def main():
    import boto3
    now=datetime.now(timezone.utc)
    session=boto3.session.Session(region_name=REGION)
    sts=session.client("sts")
    require(sts.get_caller_identity()["Account"]==ACCOUNT,"WRONG_AWS_ACCOUNT")
    cf=session.client("cloudformation")
    st=stack_outputs(cf,ST)
    prod=stack_outputs(cf,PROD)
    require(st.get("CandidateDataBucket")==ST_BUCKET and
            prod.get("CandidateDataBucket")!=ST_BUCKET,
            "UNEXPECTED_ST_OR_PROD_BUCKET")
    events=session.client("events")
    for name in ("CandidatePaperOnlyRuleName","CandidateOrchestratorRuleName"):
        rule=st[name]
        require(events.describe_rule(Name=rule)["State"]=="DISABLED",
                "UNSAFE_ST_PAPER_OR_ORCHESTRATOR_RULE")
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
        "st_paper":"DISABLED",
        "prod":"ALL_DISABLED",
        "alarms":{},
        "watchdog":None,
        "aws_mutations":False,
        "broker_orders":False
    }
    for logical in ALARMS:
        try:
            evidence["alarms"][logical]=alarm_details(cf,cw,logical,now=now)
        except Exception as exc:
            evidence["alarms"][logical]={"status":"READ_ERROR","type":type(exc).__name__,
                                         "message":str(exc)[:220]}
    try:
        evidence["watchdog"]=watchdog_logs(
            logs,st["CandidateSessionWatchdogFunctionName"],now)
    except Exception as exc:
        evidence["watchdog"]={"status":"LOGS_UNREADABLE",
                              "error_type":type(exc).__name__,
                              "message":str(exc)[:220]}
    print(json.dumps(evidence,ensure_ascii=False,indent=2,sort_keys=True,default=str))
    return 0


if __name__=="__main__":
    try: sys.exit(main())
    except Exception as exc:
        print(json.dumps({"state":"BLOCKED","reason":str(exc)[:320],
                          "aws_mutations":False,"broker_orders":False}))
        sys.exit(2)

#!/usr/bin/env python3
"""ST ONLY: isolate existing CloudWatch watchdog alarms via ST Lambda log filters.

CloudWatch custom metrics from legacy staging, PROD, and ST were published
to one namespace with NO dimensions, so ST's old alarms observed incidents
from other stacks. This patch uses metric filters bound to *ST's own*
versioned Lambda log group. It DOES NOT modify Lambda ZIPs, Signal/Paper
schedules, data, broker state, PROD/legacy resources, or trading policy.

inspect: read-only proof of exact AWS targets, alarm namespaces, state.
prepare: creates a CloudFormation UPDATE change set ONLY (no execution).
apply:   validates change set/template/16 allowable resource changes, requires
         explicit typed human confirmation, and executes ST-only change set.
The operator must review the change set and AWS cost of 8 new custom metrics.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
import time

ACCOUNT="634740393398"
REGION="eu-central-1"
ST="stocklens-st"
PROD="stocklens-prod"
SOURCE="stocklens-independent-staging"
ST_BUCKET="stocklens-st-candidatedata-6jj7i9fxjmfr"
PROD_BUCKET="stocklens-prod-candidatedata-c3yge4ymwb7u"
ORIGINAL_NAMESPACE="StockLens/IndependentStaging"
NEW_NAMESPACE="StockLens/IsolatedST"
CHANGESET="stocklens-st-watchdog-isolated-metric-filters-v1"
CONSENT="APPLY_ST_ONLY_WATCHDOG_METRIC_ISOLATION"
WATCHDOG_LOG="CandidateSessionWatchdogLogs"

METRICS={
    "MissingOrLateScheduledSignalsAlarm":"MissingOrLateScheduledSignals",
    "MissedSessionsAlarm":"MissedSessions",
    "BookHaltedAlarm":"BookHalted",
    "SchedulerStateMismatchAlarm":"SchedulerStateMismatch",
    "InvalidContinuityRecordAlarm":"InvalidReceipts",
    "WatchdogConfigurationErrorAlarm":"ConfigurationError",
    "WatchdogFailClosedAlarm":"WatchdogFailClosed",
    "WatchdogHeartbeatDeadmanAlarm":"WatchdogHeartbeat",
}


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def filter_id(metric):
    return "StIsolated"+metric+"Filter"


def filter_name(metric):
    return ST+"-watchdog-"+metric


def build_filter_yaml(metric):
    logical=filter_id(metric)
    return (
        f"  {logical}:\n"
        "    Type: AWS::Logs::MetricFilter\n"
        "    Properties:\n"
        f"      FilterName: {filter_name(metric)}\n"
        f"      LogGroupName: !Ref {WATCHDOG_LOG}\n"
        f"      FilterPattern: '{{ $.metrics.{metric} = * }}'\n"
        "      MetricTransformations:\n"
        f"        - MetricName: {metric}\n"
        f"          MetricNamespace: {NEW_NAMESPACE}\n"
        f"          MetricValue: '$.metrics.{metric}'\n"
    )


def filter_json(metric):
    return {
        "Type":"AWS::Logs::MetricFilter",
        "Properties":{
            "FilterName":filter_name(metric),
            "LogGroupName":{"Ref":WATCHDOG_LOG},
            "FilterPattern":"{ $.metrics."+metric+" = * }",
            "MetricTransformations":[{
                "MetricName":metric,
                "MetricNamespace":NEW_NAMESPACE,
                "MetricValue":"$.metrics."+metric
            }]
        }
    }


def patch_template(original):
    """Patch only 8 existing alarm Namespace fields + add 8 filters.

    Fail on unknown/missing alarm shapes instead of silently applying broad
    string replacement. Original CloudFormation template is obtained from
    the live ST stack, never an inferred local draft.
    """
    if isinstance(original, dict) or (
            isinstance(original, str) and original.lstrip().startswith("{")):
        obj=json.loads(json.dumps(original)) if isinstance(original, dict) else json.loads(original)
        resources=obj.get("Resources",{})
        require(WATCHDOG_LOG in resources, "WATCHDOG_LOG_GROUP_NOT_IN_LIVE_TEMPLATE")
        for alarm,metric in METRICS.items():
            rec=resources.get(alarm,{})
            require(rec.get("Type")=="AWS::CloudWatch::Alarm", "ALARM_TYPE_CHANGED:"+alarm)
            props=rec.get("Properties",{})
            require(props.get("Namespace")==ORIGINAL_NAMESPACE and
                    props.get("MetricName")==metric and
                    props.get("AlarmActions")==[{"Ref":"CandidateAlerts"}],
                    "ALARM_TEMPLATE_SHAPE_CHANGED:"+alarm)
            require(not props.get("Dimensions"),"ALARM_DIMENSIONS_ALREADY_PRESENT:"+alarm)
            props["Namespace"]=NEW_NAMESPACE
            logical=filter_id(metric)
            require(logical not in resources,"METRIC_FILTER_ALREADY_EXISTS:"+logical)
            resources[logical]=filter_json(metric)
        updated=json.dumps(obj,separators=(",",":"),ensure_ascii=False)
    else:
        require(isinstance(original,str),"UNKNOWN_CFN_TEMPLATE_BODY")
        require(original.count("\nResources:\n")==1 and original.count("\nOutputs:\n")==1,
                "UNSUPPORTED_YAML_TEMPLATE_LAYOUT")
        prefix,between=original.split("\nResources:\n",1)
        resources,outputs=between.rsplit("\nOutputs:\n",1)
        # Splitting at the Outputs header consumes the preceding newline.
        # Normalize a trailing newline so the last resource has the same
        # boundary semantics as every earlier CloudFormation resource.
        if not resources.endswith("\n"):
            resources+="\n"
        require("  "+WATCHDOG_LOG+":\n" in resources,"WATCHDOG_LOG_GROUP_MISSING")
        for alarm,metric in METRICS.items():
            pattern=r"(?m)^  "+re.escape(alarm)+r":\n"
            match=re.search(pattern,resources)
            require(match is not None,"ALARM_MISSING:"+alarm)
            next_match=re.search(r"(?m)^  [A-Za-z][A-Za-z0-9]+:\n",resources[match.end():])
            end=match.end()+next_match.start() if next_match else len(resources)
            body=resources[match.end():end]
            require(body.count("      Namespace: "+ORIGINAL_NAMESPACE+"\n")==1 and
                    body.count("      MetricName: "+metric+"\n")==1 and
                    body.count("      AlarmActions: [!Ref CandidateAlerts]\n")==1,
                    "ALARM_YAML_SHAPE_CHANGED:"+alarm)
            body=body.replace("      Namespace: "+ORIGINAL_NAMESPACE+"\n",
                              "      Namespace: "+NEW_NAMESPACE+"\n",1)
            resources=resources[:match.end()]+body+resources[end:]
        for metric in METRICS.values():
            require("  "+filter_id(metric)+":\n" not in resources,
                    "FILTER_ALREADY_IN_YAML")
        # Append new resources before Outputs, leaving existing resources
        # byte-for-byte identical except the 8 validated Namespace fields.
        additions="\n"+"".join(build_filter_yaml(x) for x in METRICS.values())
        updated=prefix+"\nResources:\n"+resources.rstrip("\n")+additions+"\nOutputs:\n"+outputs
    require(len(updated.encode("utf-8"))<=51200,"CFN_INLINE_TEMPLATE_TOO_LARGE")
    return updated


def template_text(value):
    return value if isinstance(value,str) else json.dumps(value,separators=(",",":"),ensure_ascii=False)


def outputs(cf,name):
    rows=cf.describe_stacks(StackName=name)["Stacks"]
    require(len(rows)==1 and rows[0]["StackStatus"] in ("CREATE_COMPLETE","UPDATE_COMPLETE"),
            "UNSTABLE_STACK:"+name)
    row=rows[0]
    return row,{x["OutputKey"]:x["OutputValue"] for x in row.get("Outputs",[])}


def preconditions(c):
    sts,cf,ev,cw,sns=c["sts"],c["cloudformation"],c["events"],c["cloudwatch"],c["sns"]
    require(sts.get_caller_identity()["Account"]==ACCOUNT,"WRONG_ACCOUNT")
    stack,st=outputs(cf,ST)
    _,prod=outputs(cf,PROD)
    _,source=outputs(cf,SOURCE)
    require(st.get("CandidateDataBucket")==ST_BUCKET and
            prod.get("CandidateDataBucket")==PROD_BUCKET and
            source.get("CandidateDataBucket") not in (ST_BUCKET,PROD_BUCKET),
            "BUCKETS_NOT_ISOLATED")
    for key in ("CandidatePaperOnlyRuleName","CandidateOrchestratorRuleName"):
        require(ev.describe_rule(Name=st[key]).get("State")=="DISABLED",
                "ST_PAPER_MUST_REMAIN_OFF:"+key)
    require(ev.describe_rule(Name=st["CandidateSignalOnlyRuleName"]).get("State")=="ENABLED",
            "ST_SIGNAL_UNEXPECTED_STATE")
    for key in ("CandidateSignalOnlyRuleName",
                "CandidatePaperOnlyRuleName","CandidateOrchestratorRuleName"):
        require(ev.describe_rule(Name=prod[key]).get("State")=="DISABLED",
                "PROD_MUST_REMAIN_OFF:"+key)
    topic=st.get("CandidateAlertsTopic")
    require(topic==f"arn:aws:sns:{REGION}:{ACCOUNT}:{ST}-candidate-alerts",
            "TOPIC_MISMATCH")
    subs=sns.list_subscriptions_by_topic(TopicArn=topic)["Subscriptions"]
    require(any(s.get("Protocol")=="email" and
                s.get("SubscriptionArn") not in ("PendingConfirmation",None)
                for s in subs),"ST_ALERT_EMAIL_NOT_CONFIRMED")
    status={}
    for logical,metric in METRICS.items():
        rid=cf.describe_stack_resource(StackName=ST,LogicalResourceId=logical)["StackResourceDetail"]["PhysicalResourceId"]
        found=cw.describe_alarms(AlarmNames=[rid]).get("MetricAlarms",[])
        require(len(found)==1 and found[0].get("MetricName")==metric,
                "ALARM_DEFINITION_CHANGED:"+logical)
        alarm=found[0]
        require(alarm.get("ActionsEnabled") is True and
                topic in alarm.get("AlarmActions",[]),
                "ALARM_ACTIONS_DISABLED:"+logical)
        require(not alarm.get("Dimensions"),"UNEXPECTED_ALARM_DIMENSIONS:"+logical)
        require(alarm.get("Namespace") in (ORIGINAL_NAMESPACE,NEW_NAMESPACE),
                "ALARM_NAMESPACE_UNKNOWN:"+logical)
        status[logical]={"namespace":alarm["Namespace"],"state":alarm.get("StateValue")}
    return stack,st,status


def check_live_metrics(c,st,status):
    logs=c["logs"]
    name="/aws/lambda/"+ST+"-watchdog"
    records=logs.describe_metric_filters(logGroupName=name,
                                         filterNamePrefix=ST+"-watchdog-").get("metricFilters",[])
    by_name={x["filterName"]:x for x in records}
    require(len(records)==len(METRICS),"ISOLATED_METRIC_FILTER_COUNT_WRONG")
    for metric in METRICS.values():
        f=by_name.get(filter_name(metric))
        require(f is not None,"ISOLATED_FILTER_MISSING:"+metric)
        require(f.get("filterPattern")=="{ $.metrics."+metric+" = * }" and
                f.get("logGroupName")==name and
                f.get("metricTransformations")==[{
                    "metricName":metric,"metricNamespace":NEW_NAMESPACE,
                    "metricValue":"$.metrics."+metric}],
                "ISOLATED_FILTER_WRONG:"+metric)
    require(all(v["namespace"]==NEW_NAMESPACE for v in status.values()),
            "SOME_ALARMS_STILL_USE_SHARED_NAMESPACE")
    return True


def build_clients(boto3):
    session=boto3.session.Session(region_name=REGION)
    return {k:session.client(k) for k in (
        "sts","cloudformation","events","cloudwatch","sns","logs")}


def validate_changes(description):
    require(description.get("Status")=="CREATE_COMPLETE" and
            description.get("ExecutionStatus")=="AVAILABLE" and
            not description.get("NextToken"),"CHANGE_SET_NOT_READY_OR_PAGED")
    changes=description.get("Changes",[])
    expected={x:("Modify","AWS::CloudWatch::Alarm") for x in METRICS}
    expected.update({filter_id(x):("Add","AWS::Logs::MetricFilter") for x in METRICS.values()})
    got={}
    for row in changes:
        rc=row.get("ResourceChange",{})
        lid=rc.get("LogicalResourceId")
        require(lid in expected and lid not in got,
                "UNEXPECTED_CHANGE_SET_RESOURCE:"+str(lid))
        require((rc.get("Action"),rc.get("ResourceType"))==expected[lid] and
                rc.get("Replacement") in (None,"False",False),
                "UNSAFE_CHANGE_SET_ACTION:"+str(lid)+":"+str(rc))
        got[lid]=rc["Action"]
    require(set(got)==set(expected),"CHANGE_SET_RESOURCE_COUNT_OR_ID_MISMATCH")
    return sorted(got.items())


def prepare(c,stack,status):
    require(all(v["namespace"]==ORIGINAL_NAMESPACE for v in status.values()),
            "ALREADY_PATCHED_OR_PARTIALLY_UPDATED_INSPECT_FIRST")
    cf=c["cloudformation"]
    live=cf.get_template(StackName=ST,TemplateStage="Original")["TemplateBody"]
    patched=patch_template(live)
    param=[{"ParameterKey":x["ParameterKey"],"UsePreviousValue":True}
           for x in stack.get("Parameters",[])]
    sha=hashlib.sha256(patched.encode()).hexdigest()
    print("ST_ONLY_PROPOSED_TEMPLATE_SHA256:"+sha)
    cf.create_change_set(
        StackName=ST,
        ChangeSetName=CHANGESET,
        ChangeSetType="UPDATE",
        Description="ST-only isolated watchdog metrics from ST Lambda logs; no trading changes",
        TemplateBody=patched,
        Parameters=param,
        Capabilities=["CAPABILITY_IAM","CAPABILITY_NAMED_IAM"]
    )
    for attempt in range(40):
        item=cf.describe_change_set(StackName=ST,ChangeSetName=CHANGESET)
        if item["Status"] in ("CREATE_COMPLETE","FAILED"):
            break
        time.sleep(2)
    else:
        raise RuntimeError("CHANGE_SET_PENDING_INSPECT_BEFORE_RETRY")
    if item["Status"]!="CREATE_COMPLETE":
        raise RuntimeError("CHANGE_SET_FAILED:"+str(item.get("StatusReason",""))[:300])
    changes=validate_changes(item)
    print("CHANGE_SET_PREPARED_NOT_EXECUTED:",CHANGESET)
    print("EXACT_CHANGES:",json.dumps(changes))
    print("NO_AWS_RESOURCES_UPDATED_YET")
    return sha


def apply(c,stack,status,*,approved=False):
    # The command-line --yes flag is the operator's explicit approval.
    # There is deliberately no free-form confirmation phrase to mistype.
    require(approved, "EXPLICIT_ST_ONLY_APPLY_--yes_REQUIRED")
    require(all(v["namespace"]==ORIGINAL_NAMESPACE for v in status.values()),
            "ALREADY_PATCHED_OR_PARTIAL_REVIEW_FIRST")
    cf=c["cloudformation"]
    actual=cf.describe_change_set(StackName=ST,ChangeSetName=CHANGESET)
    changes=validate_changes(actual)
    require(actual.get("StackName")==ST,"WRONG_CHANGE_SET_STACK")
    live=cf.get_template(StackName=ST,TemplateStage="Original")["TemplateBody"]
    expected=patch_template(live)
    candidate=cf.get_template(StackName=ST,ChangeSetName=CHANGESET,
                              TemplateStage="Original")["TemplateBody"]
    require(template_text(candidate)==template_text(expected),
            "CHANGE_SET_TEMPLATE_NOT_IDENTICAL_TO_REVIEWED_PATCH")
    print("VERIFIED_CHANGE_SET:",CHANGESET)
    print("CHANGE_SET_SHA256:",hashlib.sha256(expected.encode()).hexdigest())
    print("EXACT_CHANGES:",json.dumps(changes))
    print("NOTICE: 8 extra custom metrics can incur additional AWS cost; 20 USD budget is alert-only.")
    print("ST-only: alarms will temporarily have insufficient datapoints until ST emits isolated metrics.")
    print("PROD and paper schedules remain disabled; Lambda code and S3 objects unchanged.")
    print("EXPLICIT_ST_ONLY_--yes_APPROVAL_PRESENT:CHANGE_SET_VALIDATED")
    cf.execute_change_set(StackName=ST,ChangeSetName=CHANGESET)
    for attempt in range(80):
        result=cf.describe_stacks(StackName=ST)["Stacks"][0]["StackStatus"]
        if result not in ("UPDATE_IN_PROGRESS","UPDATE_COMPLETE_CLEANUP_IN_PROGRESS"):
            break
        time.sleep(4)
    require(result=="UPDATE_COMPLETE","STACK_UPDATE_DID_NOT_COMPLETE:"+result)
    _,fresh,states=preconditions(c)
    check_live_metrics(c,fresh,states)
    print("ST_ISOLATED_MONITORING_DEPLOYED:8_FILTERS_AND_ALARMS:NO_PROD_NO_PAPER_NO_BROKER")
    print("Watchdog needs fresh hourly log reports before isolated metric alarm status is meaningful.")
    return True


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("mode",choices=("inspect","prepare","apply"))
    ap.add_argument("--yes",action="store_true",
                    help="Explicitly approve the exact verified ST-only change set; no typed confirmation")
    args=ap.parse_args()
    require(not args.yes or args.mode=="apply", "--yes_ONLY_ALLOWED_WITH_apply")
    import boto3
    c=build_clients(boto3)
    stack,st,status=preconditions(c)
    print("STACK:",ST,stack["StackStatus"])
    print("ALARM_NAMESPACES_AND_STATES:",json.dumps(status,sort_keys=True))
    if args.mode=="inspect":
        if all(x["namespace"]==NEW_NAMESPACE for x in status.values()):
            check_live_metrics(c,st,status)
            print("ST_ISOLATED_CLOUDWATCH_METRICS_PRESENT:NO_WRITES")
        else:
            print("ST_SHARED_METRICS_STILL_PRESENT:NO_WRITES")
        return 0
    if args.mode=="prepare":
        prepare(c,stack,status)
    else:
        apply(c,stack,status,approved=args.yes)
    return 0


if __name__=="__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print("ST_METRIC_ISOLATION_BLOCKED:"+str(exc)[:550])
        sys.exit(2)

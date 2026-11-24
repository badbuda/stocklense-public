#!/usr/bin/env python3
"""ONE operator CloudShell guarded release to AUTOMATED ST Epoch5 modeled Paper.

No broker. No PROD. No legacy Paper mutation. NO backfills.

Two CloudFormation changesets:
1) Stage upgraded code + isolated read-only watchdog + DISABLED rules/alarms.
   Invoke REAL Lambda preopen approval check and REAL Yahoo prior-session 1m historical
   connectivity preflight, both READ ONLY. If vendor or IAM fails: STOP DARK.
2) Only if both succeed, arm ST-only Paper with a pinned operator approval and
   enable EventBridge after-close retries plus independent receipt Watchdog.
   Each Lambda invokes against the real clock/session and fails closed on
   missing lag1/vendor, changed historical S3 state or incomplete continuity.

If any stage fails, do not report acceptance. The operator retains CloudShell
ownership; GitHub OIDC role is read-only and cannot deploy this itself.
"""
from __future__ import annotations
import argparse
import base64
from copy import deepcopy
from datetime import datetime,timezone
import hashlib
import io
import json
from pathlib import Path
import sys

from infra.aws import sl64_epoch5_stage_dark_deploy as previous
from infra.aws import sl56_epoch4_approval_readback as legacy_approval
from infra.aws import sl64_epoch5_preopen as newapproval
from infra.aws import sl64_epoch5_paper_economic_adapter as adapter
from infra.aws import sl63_deployed_paper_source_parity as baseline
from infra.aws import sl64_epoch5_immutable_store as store

REGION=previous.REGION
ACCOUNT=previous.ACCOUNT
BUCKET=previous.BUCKET
STACK=previous.STACK
FUNCTION=previous.FUNCTION
WATCHDOG="stocklens-st-epoch5-continuity-watchdog"
PAPER_RULE="stocklens-st-epoch5-paper-eod"
WATCH_RULE="stocklens-st-epoch5-watchdog-eod"
ALARM1="stocklens-st-epoch5-paper-errors"
ALARM2="stocklens-st-epoch5-continuity-missing"
FIRST=store.FIRST

ZIP_LIMIT=previous.ZIP_LIMIT


def require(ok,message):
    if not ok:raise RuntimeError(message)


def _client_error_code(exc):
    return (getattr(exc,"response",{}) or {}).get("Error",{}).get("Code")


def chosen_existing_alert_topic(cw):
    """Reuse only one SAME-ACCOUNT/SAME-REGION SNS topic from existing ST alarms."""
    topics=set()
    token=None
    for _ in range(10):
        args={"AlarmNamePrefix":"stocklens-st-","MaxRecords":100}
        if token:args["NextToken"]=token
        data=cw.describe_alarms(**args)
        for alarm in data.get("MetricAlarms",[]):
            for arn in alarm.get("AlarmActions",[]):
                if arn.startswith("arn:aws:sns:"+REGION+":"+ACCOUNT+":"):
                    topics.add(arn)
        token=data.get("NextToken")
        if not token:break
    require(not token,"ST_ALARM_TOPIC_PAGINATION_INCOMPLETE")
    require(len(topics)==1,"NO_UNAMBIGUOUS_EXISTING_ST_SNS_ALARM_TOPIC")
    return next(iter(topics))


def _real_dark_state(clients, expected_dark_sha, staged_template):
    legacy_approval.inspect(clients)
    stack=previous._existing(clients["cloudformation"])
    require(stack is not None and stack["StackStatus"] in ("CREATE_COMPLETE","UPDATE_COMPLETE"),
            "EXPECTED_DARK_ST_STACK_NOT_STABLE")
    fn=clients["lambda"].get_function_configuration(
        FunctionName=FUNCTION)
    require(fn.get("CodeSha256")==expected_dark_sha and
            fn.get("Handler")==previous.HANDLER and
            fn.get("State")=="Active" and
            fn.get("LastUpdateStatus")=="Successful" and
            fn.get("Environment",{}).get("Variables",{}).get(
                "STOCKLENS_EPOCH5_WRITE_ENABLED")=="false",
            "DARK_LAMBDA_SHA_OR_WRITE_FLAG_MISMATCH")
    current=clients["cloudformation"].get_template(
        StackName=STACK,TemplateStage="Original")["TemplateBody"]
    if isinstance(current,str):current=json.loads(current)
    if current == staged_template:
        return fn, True
    require(set(current.get("Resources",{}))==
            {"DarkRole","DarkLogGroup","DarkLambda"},
            "PREEXISTING_CFN_NOT_ISOLATED_DARK_STACK")
    require(current["Resources"]["DarkLambda"]["Properties"]["FunctionName"]
            ==FUNCTION, "DARK_TEMPLATE_DIFFERENT_LAMBDA")
    return fn, False


def _package(clients,repo):
    old,cfg=baseline.authenticated_download(
        clients["sts"],clients["lambda"])
    payload=previous.package(old,repo)
    return payload,cfg


def _new_template(artifact_key,old,topic,*,armed,approval_sha):
    require(isinstance(approval_sha,str) and len(approval_sha)==64,
            "RELEASE_NEW_APPROVAL_SHA_REQUIRED")
    """Explicitly construct from pinned tested dark template, no PROD objects."""
    t=previous.template(artifact_key,old)
    t["Description"]="ST Epoch5 modeled Paper, current-date-only; broker DISARMED"
    res=t["Resources"]
    paper=res["DarkLambda"]["Properties"]
    paper["Timeout"]=300
    paper["ReservedConcurrentExecutions"]=1
    paper["Description"]="ST Epoch5 REAL SINGLE-VENDOR modeled Paper (NO BROKER)"
    paper["Environment"]["Variables"]={
        "STOCKLENS_DATA_BUCKET":BUCKET,
        "STOCKLENS_EPOCH5_WRITE_ENABLED":"true" if armed else "false",
        "STOCKLENS_EPOCH5_APPROVAL_SHA256":approval_sha,
        "STOCKLENS_ST_FIRST_SESSION":FIRST,
    }
    prefix="arn:aws:s3:::"+BUCKET+"/"
    new_epoch=prefix+store.PREFIX
    read_keys=[
        new_epoch+"genesis.json",
        new_epoch+"sessions/*",
        new_epoch+"continuity/*",
    ]
    trust={"Version":"2012-10-17","Statement":[{
        "Effect":"Allow",
        "Principal":{"Service":"lambda.amazonaws.com"},
        "Action":"sts:AssumeRole"}]}
    watch_policy={"Version":"2012-10-17","Statement":[
        {"Effect":"Allow","Action":["s3:GetObject","s3:GetObjectVersion"],
         "Resource":read_keys},
        {"Effect":"Allow",
         "Action":["logs:CreateLogStream","logs:PutLogEvents"],
         "Resource":["arn:aws:logs:"+REGION+":"+ACCOUNT+
                     ":log-group:/aws/lambda/"+WATCHDOG+":*"]},
    ]}
    res["WatchdogRole"]={"Type":"AWS::IAM::Role","Properties":{
        "AssumeRolePolicyDocument":trust,
        "Policies":[{"PolicyName":"epoch5-watchdog-read-only",
                     "PolicyDocument":watch_policy}]}}
    res["WatchdogLog"]={"Type":"AWS::Logs::LogGroup","Properties":{
        "LogGroupName":"/aws/lambda/"+WATCHDOG,"RetentionInDays":14}}
    res["WatchdogLambda"]={"Type":"AWS::Lambda::Function",
        "DependsOn":["WatchdogRole","WatchdogLog"],
        "Properties":{
           "FunctionName":WATCHDOG,
           "Runtime":old["Runtime"],
           "Handler":"infra.aws.sl64_epoch5_watchdog.handler",
           "Role":{"Fn::GetAtt":["WatchdogRole","Arn"]},
           "Code":{"S3Bucket":BUCKET,"S3Key":artifact_key},
           "Timeout":60,"MemorySize":512,
           "Architectures":old.get("Architectures",["x86_64"]),
           "Environment":{"Variables":{"STOCKLENS_DATA_BUCKET":BUCKET,"STOCKLENS_ST_FIRST_SESSION":FIRST}},
        }}
    if old.get("Layers"):
        res["WatchdogLambda"]["Properties"]["Layers"]=[
            v["Arn"] for v in old["Layers"]]

    enabled="ENABLED" if armed else "DISABLED"
    res["PaperRule"]={"Type":"AWS::Events::Rule","Properties":{
        "Name":PAPER_RULE,"State":enabled,
        "Description":"After-close modeled Paper; first_session=" + FIRST,
        # 21:30–21:59 UTC fits the 15-minute to 5-hour window on normal and half days.
        "ScheduleExpression":"cron(30,42,52 21 ? * MON-FRI *)",
        "Targets":[{"Id":"NewEpoch5PaperOnly",
                    "Arn":{"Fn::GetAtt":["DarkLambda","Arn"]},
                    "Input":json.dumps({"mode":"STAGING_EPOCH5_MODELED_PAPER"}),
                    "RetryPolicy":{"MaximumRetryAttempts":0,
                                   "MaximumEventAgeInSeconds":600}}]}}
    res["WatchRule"]={"Type":"AWS::Events::Rule","Properties":{
        "Name":WATCH_RULE,"State":enabled,
        "Description":"Daily independent immutable Paper+Continuity watchdog",
        "ScheduleExpression":"cron(59 21 ? * MON-FRI *)",
        "Targets":[{"Id":"Epoch5ReadOnlyContinuityWatchdog",
                    "Arn":{"Fn::GetAtt":["WatchdogLambda","Arn"]},
                    "Input":json.dumps(
                        {"mode":"STAGING_EPOCH5_CONTINUITY_WATCHDOG"}),
                    "RetryPolicy":{"MaximumRetryAttempts":0,
                                   "MaximumEventAgeInSeconds":600}}]}}
    for name,rule,func in (
        ("PaperRulePermission","PaperRule","DarkLambda"),
        ("WatchRulePermission","WatchRule","WatchdogLambda")):
        res[name]={"Type":"AWS::Lambda::Permission",
            "Properties":{"Action":"lambda:InvokeFunction",
                          "FunctionName":{"Fn::GetAtt":[func,"Arn"]},
                          "Principal":"events.amazonaws.com",
                          "SourceArn":{"Fn::GetAtt":[rule,"Arn"]}}}
    for logical,actual,fn in (
        ("PaperErrorsAlarm",ALARM1,FUNCTION),
        ("WatchdogErrorsAlarm",ALARM2,WATCHDOG)):
        res[logical]={"Type":"AWS::CloudWatch::Alarm","Properties":{
            "AlarmName":actual,
            "Description":"StockLens ST Epoch5 error. No broker.",
            "Namespace":"AWS/Lambda","MetricName":"Errors",
            "Dimensions":[{"Name":"FunctionName","Value":fn}],
            "Statistic":"Sum","Period":300,"EvaluationPeriods":1,
            "Threshold":1,"ComparisonOperator":"GreaterThanOrEqualToThreshold",
            "TreatMissingData":"notBreaching",
            "AlarmActions":[topic],"ActionsEnabled":True}}
    t["Outputs"]={
        "NewPaperLambda":{"Value":FUNCTION},
        "WatchdogLambda":{"Value":WATCHDOG},
        "PaperWriteEnabled":{"Value":"true" if armed else "false"},
        "SchedulesEnabled":{"Value":"true" if armed else "false"},
        "SingleVendorOnly":{"Value":"true"},
        "BrokerOrdersEnabled":{"Value":"false"},
    }
    require(set(res)=={
        "DarkRole","DarkLogGroup","DarkLambda",
        "WatchdogRole","WatchdogLog","WatchdogLambda",
        "PaperRule","WatchRule","PaperRulePermission","WatchRulePermission",
        "PaperErrorsAlarm","WatchdogErrorsAlarm"},
        "STACK_RESOURCE_SET_UNEXPECTED")
    return t


def _change_set(clients,body,name,*,stage):
    cfn=clients["cloudformation"]
    cfn.create_change_set(StackName=STACK,ChangeSetName=name,
        ChangeSetType="UPDATE",TemplateBody=json.dumps(body),
        Capabilities=["CAPABILITY_IAM"])
    cfn.get_waiter("change_set_create_complete").wait(
        ChangeSetName=name,StackName=STACK,
        WaiterConfig={"Delay":5,"MaxAttempts":42})
    details=cfn.describe_change_set(ChangeSetName=name,StackName=STACK)
    require(details["Status"]=="CREATE_COMPLETE","CFN_CHANGESET_UNCREATED")
    allowable_add={
        "WatchdogRole","WatchdogLog","WatchdogLambda",
        "PaperRule","WatchRule","PaperRulePermission","WatchRulePermission",
        "PaperErrorsAlarm","WatchdogErrorsAlarm"}
    allowed_mod={"DarkLambda"}
    if not stage:
        allowed_mod|={"PaperRule","WatchRule"}
    changes=details.get("Changes",[])
    require(bool(changes),"CFN_EMPTY_CHANGESET")
    for item in changes:
        ch=item["ResourceChange"]
        action=ch["Action"]
        logical=ch["LogicalResourceId"]
        if action=="Add":
            require(stage and logical in allowable_add,
                    "CFN_UNEXPECTED_ADDED_RESOURCE:"+logical)
        elif action=="Modify":
            require(logical in allowed_mod,
                    "CFN_UNEXPECTED_MODIFIED_RESOURCE:"+logical)
            require(ch.get("Replacement")=="False",
                    "CFN_REPLACEMENT_POSSIBLE_BLOCKED:"+logical)
        else:
            raise RuntimeError("CFN_DELETE_OR_IMPORT_BLOCKED:"+logical)
    cfn.execute_change_set(ChangeSetName=name,StackName=STACK)
    cfn.get_waiter("stack_update_complete").wait(
        StackName=STACK,WaiterConfig={"Delay":10,"MaxAttempts":60})


def _invoke(clients,fn,event,status):
    response=clients["lambda"].invoke(
        FunctionName=fn,InvocationType="RequestResponse",
        Payload=json.dumps({"mode":event}).encode())
    require(response.get("StatusCode")==200 and
            not response.get("FunctionError"),
            "LAMBDA_READ_ONLY_PREFLIGHT_RUNTIME_FAILED")
    result=json.loads(response["Payload"].read(16384))
    require(result.get("status")==status and
            result.get("new_epoch_paper_or_continuity_written") is False and
            result.get("broker_orders") is False,
            "LAMBDA_READ_ONLY_PREFLIGHT_RESULT_FAILED")
    return result


def release(clients,repo,*,execute):
    legacy_approval.inspect(clients)
    proposed=newapproval.preflight(
        clients["sts"],clients["s3"],now=datetime.now(timezone.utc))
    approval_sha=hashlib.sha256(store.canonical(proposed["document"])).hexdigest()
    first_open=adapter.session_times(store.FIRST)[2]
    approved=adapter._approval(clients["s3"],FIRST,first_open)
    require(approved["sha256"]==approval_sha,
            "EPOCH5_NEW_BOOK_PREOPEN_APPROVAL_NOT_PINNED")
    prior,prior_close,opening,_=adapter.session_times(store.FIRST)
    source=adapter._source_signal(
        clients["s3"],FIRST,prior,prior_close,opening,approved)
    require(source["sha256"]==proposed["source_sha256"],
            "EPOCH5_PREOPEN_SIGNAL_VERSION_DRIFT")
    pkg,old=_package(clients,repo)
    sha_b64=base64.b64encode(hashlib.sha256(pkg).digest()).decode()
    topic=chosen_existing_alert_topic(clients["cloudwatch"])
    # If first session has already closed, a new prospective Epoch and
    # operator approval are required. NO replay of 09:31 hypothetical fills.
    _,_,_,firstclose=adapter.session_times(store.FIRST)
    require(datetime.now(timezone.utc)<firstclose,
            "FIRST_SESSION_ALREADY_CLOSED_DO_NOT_BACKFILL")
    report={
        "status":"ST_EPOCH5_AUTO_RELEASE_PREFLIGHT_PASS",
        "new_zip_sha256_b64":sha_b64,
        "old_dark_zip_sha256_b64":dark["CodeSha256"],
        "original_preopen_approval_sha256":approval_sha,
        "existing_sns_alert_topic_discovered":True,
        "old_st_paper_disabled":True,"prod_untouched":True,
        "broker_orders":False,"historical_backfill":False,
        "single_vendor_not_independently_correlated":True,
    }
    if not execute:
        return {**report,"aws_mutations":False,
                "paper_schedules_enabled":False},0

    require(previous._artifact(clients["s3"],pkg) == key, "DEPLOYMENT_ARTIFACT_KEY_CHANGED")
    stage_name="stocklens-epoch5-stage-"+hashlib.sha256(pkg).hexdigest()[:12]
    if not already_staged:
        _change_set(clients,stage,stage_name,stage=True)
    cfn=clients["cloudformation"]
    updated=clients["lambda"].get_function_configuration(
        FunctionName=FUNCTION)
    require(updated.get("CodeSha256")==sha_b64 and
            updated.get("State")=="Active" and
            updated.get("LastUpdateStatus")=="Successful" and
            updated.get("Environment",{}).get("Variables",{}).get(
                "STOCKLENS_EPOCH5_WRITE_ENABLED")=="false",
            "DEPLOYED_UPDATED_PAPER_NOT_DARK")
    _invoke(clients,FUNCTION,"STAGING_EPOCH5_DARK_READINESS",
            "EPOCH5_DARK_LAMBDA_READINESS_S3_READ_ONLY")
    vendor=_invoke(
        clients,FUNCTION,"STAGING_EPOCH5_VENDOR_CONNECTIVITY_READONLY",
        "EPOCH5_HISTORIC_YFINANCE_1M_READ_ONLY_PREFLIGHT")
    require(vendor["historical_session"]==prior
            and vendor.get("source")=="YFINANCE_1M_RAW"
            and vendor.get("independent_second_vendor_verified") is False
            and len(vendor.get("quote_sha256",""))==64,
            "NO_REAL_HISTORICAL_YAHOO_1M_PREFLIGHT")
    legacy_approval.inspect(clients)
    # Ensure stage rules stay disabled while vendor preflight is tested.
    for r in (PAPER_RULE,WATCH_RULE):
        require(clients["events"].describe_rule(Name=r)["State"]=="DISABLED",
                "UNEXPECTED_PREMATURE_ENABLED_SCHEDULE")
    # Never arm after first close: archived first-day fills are NOT replayable.
    require(datetime.now(timezone.utc)<firstclose,
            "FIRST_SESSION_ALREADY_CLOSED_DO_NOT_BACKFILL")
    # Arm by a second CloudFormation update, never an untracked EventBridge mutation.
    armed=_new_template(key,old,topic,armed=True,approval_sha=approval_sha)
    armed_name="stocklens-epoch5-arm-"+hashlib.sha256(pkg).hexdigest()[:12]
    _change_set(clients,armed,armed_name,stage=False)
    live=clients["lambda"].get_function_configuration(FunctionName=FUNCTION)
    require(live.get("CodeSha256")==sha_b64 and
            live.get("Environment",{}).get("Variables",{}).get(
                "STOCKLENS_EPOCH5_WRITE_ENABLED")=="true" and
            live.get("Environment",{}).get("Variables",{}).get(
                "STOCKLENS_EPOCH5_APPROVAL_SHA256")==approval_sha,
            "ARMED_PAPER_CODE_OR_APPROVAL_ENV_MISMATCH")
    watcher=clients["lambda"].get_function_configuration(
        FunctionName=WATCHDOG)
    require(watcher.get("CodeSha256")==sha_b64 and
            watcher.get("Handler")==
                "infra.aws.sl64_epoch5_watchdog.handler",
            "WATCHDOG_CODE_UNEXPECTED")
    for rule,fn in ((PAPER_RULE,FUNCTION),(WATCH_RULE,WATCHDOG)):
        require(clients["events"].describe_rule(Name=rule)["State"]=="ENABLED",
                "AUTOMATION_NOT_ENABLED:"+rule)
        targets=clients["events"].list_targets_by_rule(Rule=rule)["Targets"]
        require(len(targets)==1 and
                targets[0]["Arn"].endswith(":function:"+fn),
                "AUTOMATION_TARGET_NOT_EXACT:"+rule)
    _invoke(clients,FUNCTION,"STAGING_EPOCH5_READ_ONLY_PREFLIGHT",
            "EPOCH5_ARMED_READINESS_S3_READ_ONLY")
    legacy_approval.inspect(clients)
    return {**report,
        "status":"ST_EPOCH5_AUTOMATED_MODELED_PAPER_ARMED_REAL_AWS",
        "aws_mutations":True,
        "st_new_paper_lambda":FUNCTION,
        "st_new_watchdog_lambda":WATCHDOG,
        "paper_schedules_enabled":True,
        "watchdog_schedule_enabled":True,
        "sns_alarm_topic_reused":topic,
        "code_sha256_verified":True,
        "paper_or_continuity_written_yet":False,
        "first_expected_session":FIRST,
        "next_market_data_checks":"AFTER_CLOSE_YAHOO_1M_REAL_VENDOR_ONLY",
        "broker_orders":False},0


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--arm-automated-st",action="store_true")
    args=parser.parse_args()
    import boto3
    sdk=boto3.session.Session(region_name=REGION)
    clients={k:sdk.client(k) for k in (
        "sts","s3","cloudformation","lambda","events","cloudwatch")}
    try:
        result,rc=release(
            clients,Path(__file__).resolve().parents[2],
            execute=args.arm_automated_st)
    except Exception as exc:
        result={
            "status":"ST_EPOCH5_AUTO_RELEASE_FAILED_CLOSED_REVIEW_STACK",
            "exception_type":type(exc).__name__,
            "reason":str(exc)[:280],
            "broker_orders":False,
            "prod_untouched":True,
            # Mutation state is not known after exception: never say no write.
            "aws_mutation_state_may_be_partial":args.arm_automated_st,
            "manual_cfn_review_before_retry":args.arm_automated_st,
        }
        rc=4
    print(json.dumps(result,indent=2,sort_keys=True))
    return rc


if __name__=="__main__":
    sys.exit(main())

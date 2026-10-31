#!/usr/bin/env python3
"""ST-only one-shot CloudFormation monitoring repair + guarded Paper schedule enablement.

One narrowly reviewed CloudFormation change set (watchdog Lambda environment plus
its CloudFormation-derived permission and scheduled target) and then one ST-only
EventBridge EnableRule via separately pinned guard.
No PROD/Signal/Broker/Paper-book writes, no legacy DynamoDB changes.
Fails closed on every unknown template, planned resource, permission, or state.
"""
import hashlib
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

REGION="eu-central-1"
ACCOUNT="634740393398"
STACK="stocklens-st"
PROD="stocklens-prod"
SESSION="2026-10-30"
BUCKET="stocklens-st-candidatedata-6jj7i9fxjmfr"
RULE_CRON="cron(20 3 ? * TUE-SAT *)"
GUARD_URL=("https://raw.githubusercontent.com/badbuda/stocklense-public/"
           "73c8868fbdec1175c37d634a2fa70fe8104a3751/"
           "infra/aws/enable_st_paper_once_guarded.py")
GUARD_BLOB="f6af36b16fe5965cededb4757f2b8cc6f3bb81a1"
CHANGE="stocklens-st-paper-monitoring-20261030"

def require(test, reason):
    if not test:
        raise RuntimeError(reason)

def main():
    import boto3
    b=boto3.Session(region_name=REGION)
    sts=b.client("sts")
    cf=b.client("cloudformation")
    ev=b.client("events")
    lm=b.client("lambda")
    from botocore.exceptions import ClientError
    require(sts.get_caller_identity()["Account"]==ACCOUNT,"WRONG_AWS_ACCOUNT")
    def describe(name):
        a=cf.describe_stacks(StackName=name)["Stacks"]
        require(len(a)==1 and a[0]["StackStatus"] in ("CREATE_COMPLETE","UPDATE_COMPLETE"),"STACK_NOT_STABLE:"+name)
        s=a[0]
        return s,{x["OutputKey"]:x["OutputValue"] for x in s.get("Outputs",[])}
    s,out=describe(STACK)
    _,pout=describe(PROD)
    require(out.get("CandidateDataBucket")==BUCKET and pout.get("CandidateDataBucket")!=BUCKET,
            "ST_PROD_BUCKET_ISOLATION_FAILED")
    for outs,key,state in ((out,"CandidateSignalOnlyRuleName","ENABLED"),
                           (out,"CandidateOrchestratorRuleName","DISABLED"),
                           (pout,"CandidateSignalOnlyRuleName","DISABLED"),
                           (pout,"CandidatePaperOnlyRuleName","DISABLED"),
                           (pout,"CandidateOrchestratorRuleName","DISABLED")):
        require(ev.describe_rule(Name=outs[key])["State"]==state,
                "UNSAFE_RULE:"+key)
    paper_rule=ev.describe_rule(Name=out["CandidatePaperOnlyRuleName"])
    require(paper_rule["State"] in ("DISABLED","ENABLED")
            and paper_rule.get("ScheduleExpression")==RULE_CRON,
            "UNSAFE_ST_PAPER_RULE")
    ps={p["ParameterKey"]:p.get("ParameterValue","") for p in s.get("Parameters",[])}
    require("MonitoringStartSession" in ps,"MONITORING_PARAMETER_NOT_IN_DEPLOYED_TEMPLATE")
    require(ps["MonitoringStartSession"] in ("",SESSION),
            "MONITORING_CONFIG_HAS_OTHER_START_DATE:"+ps["MonitoringStartSession"])
    expected=out.get("CandidateSessionWatchdogFunctionName")
    require(bool(expected),"WATCHDOG_FUNCTION_OUTPUT_MISSING")
    if ps["MonitoringStartSession"]!=SESSION:
        # Use the deployed template; all other parameters retain their values.
        # Deliberately refuse to update a stack that already drifted in the rule states.
        params=[{"ParameterKey":k, "ParameterValue":SESSION}
                if k=="MonitoringStartSession" else
                {"ParameterKey":k, "UsePreviousValue":True} for k in ps]
        require(sum(p["ParameterKey"]=="MonitoringStartSession" for p in params)==1,
                "BAD_PARAMETER_DIFF")
        # This exact change set was already created by the first fail-closed
        # run. Reuse and inspect it rather than automatically creating a second.
        try:
            z=cf.describe_change_set(StackName=STACK,ChangeSetName=CHANGE)
            print("REVIEW_EXISTING_ST_CHANGE_SET:"+CHANGE,flush=True)
        except ClientError as exc:
            code=exc.response.get("Error",{}).get("Code","")
            require(code=="ChangeSetNotFoundException",
                    "CANNOT_READ_EXISTING_CHANGE_SET:"+code)
            print("CREATING_ST_MONITORING_CHANGE_SET:ONLY:"+SESSION,flush=True)
            cf.create_change_set(StackName=STACK,ChangeSetName=CHANGE,
                ChangeSetType="UPDATE",UsePreviousTemplate=True,
                Capabilities=["CAPABILITY_IAM","CAPABILITY_NAMED_IAM"],
                Parameters=params,
                Description="ST-only: set Paper monitoring genesis 2026-10-30; do not alter schedules")
            deadline=time.monotonic()+180
            while time.monotonic()<deadline:
                z=cf.describe_change_set(StackName=STACK,ChangeSetName=CHANGE)
                if z["Status"] in ("CREATE_COMPLETE","FAILED"): break
                time.sleep(3)
        require(z["Status"]=="CREATE_COMPLETE"
                and z.get("ExecutionStatus")=="AVAILABLE",
                "CHANGE_SET_NOT_EXECUTABLE:"+z.get("Status","")+":"+z.get("ExecutionStatus",""))
        require(z.get("StackId")==s.get("StackId"),"CHANGE_SET_OTHER_STACK")
        require(z.get("Description")==
                "ST-only: set Paper monitoring genesis 2026-10-30; do not alter schedules",
                "CHANGE_SET_DESCRIPTION_MISMATCH")
        planned={p["ParameterKey"]:p for p in z.get("Parameters",[])}
        require(set(planned)==set(ps),"CHANGE_SET_PARAMS_MISMATCH")
        for k,v in planned.items():
            if k=="MonitoringStartSession":
                require(v.get("ParameterValue")==SESSION,"CHANGE_SET_MONITORING_DATE_WRONG")
            else:
                require(v.get("ParameterValue",ps[k])==ps[k],
                        "CHANGE_SET_PARAMETER_CHANGED:"+k)
        changes=[c["ResourceChange"] for c in z.get("Changes",[])
                 if "ResourceChange" in c]
        changes_by_id={c["LogicalResourceId"]:c for c in changes}
        allowed={
            "CandidateSessionWatchdogLambda":
                ("AWS::Lambda::Function","False","Environment"),
            "CandidateSessionWatchdogPermission":
                ("AWS::Lambda::Permission","Conditional","SourceArn"),
            "CandidateSessionWatchdogSchedule":
                ("AWS::Events::Rule","False","Targets"),
        }
        require(len(changes)==3 and set(changes_by_id)==set(allowed),
                "UNEXPECTED_CHANGE_SET_RESOURCES:"+str(changes))
        for lid,(rtype,replacement,property_name) in allowed.items():
            c=changes_by_id[lid]
            require(c.get("Action")=="Modify" and c.get("ResourceType")==rtype
                    and c.get("Replacement")==replacement
                    and c.get("Scope")==["Properties"],
                    "UNSAFE_CHANGE_SET_RESOURCE:"+str(c))
            details=c.get("Details",[])
            require(details and all(d.get("Target",{}).get("Attribute")=="Properties"
                    and d.get("Target",{}).get("Name")==property_name
                    for d in details),"UNSAFE_CHANGE_SET_PROPERTY:"+str(c))
            require(any(d.get("Evaluation")=="Static" and
                    d.get("CausingEntity")=="MonitoringStartSession"
                    for d in details) if lid=="CandidateSessionWatchdogLambda"
                    else all(d.get("Evaluation")=="Dynamic" for d in details),
                    "UNEXPECTED_CHANGE_CAUSE:"+str(c))
        # Verify the actual existing resources, not only CFN's symbolic changes.
        def physical(logical):
            d=cf.describe_stack_resource(StackName=STACK,
                LogicalResourceId=logical)["StackResourceDetail"]
            require(d.get("ResourceStatus") in ("CREATE_COMPLETE","UPDATE_COMPLETE"),
                    "WATCHDOG_RESOURCE_UNSTABLE:"+logical)
            return d["PhysicalResourceId"]
        watchdog_rule_name=physical("CandidateSessionWatchdogSchedule")
        watchdog_function_name=physical("CandidateSessionWatchdogLambda")
        require(watchdog_function_name==expected,"WATCHDOG_LAMBDA_ID_CHANGED")
        wr=ev.describe_rule(Name=watchdog_rule_name)
        require(wr.get("State")=="ENABLED" and wr.get("ScheduleExpression")=="rate(1 hour)",
                "WATCHDOG_RULE_NOT_HOURLY_ENABLED")
        targets=ev.list_targets_by_rule(Rule=watchdog_rule_name).get("Targets",[])
        watch_fn_arn=lm.get_function_configuration(FunctionName=expected)["FunctionArn"]
        require(len(targets)==1 and targets[0].get("Id")=="SessionWatchdog"
                and targets[0].get("Arn")==watch_fn_arn,
                "WATCHDOG_WRONG_TARGET")
        print("CHANGE_SET_APPROVED:ST_WATCHDOG_LAMBDA_PERMISSION_SCHEDULE_ONLY",flush=True)
        cf.execute_change_set(StackName=STACK,ChangeSetName=CHANGE)
        cf.get_waiter("stack_update_complete").wait(StackName=STACK,
             WaiterConfig={"Delay":10,"MaxAttempts":60})
        s,out=describe(STACK)
        ps={p["ParameterKey"]:p.get("ParameterValue","") for p in s.get("Parameters",[])}
        require(ps.get("MonitoringStartSession")==SESSION,"PARAMETER_UPDATE_NOT_VERIFIED")
        require(lm.get_function_configuration(FunctionName=expected)
                .get("Environment",{}).get("Variables",{})
                .get("MONITORING_START_SESSION")==SESSION,
                "WATCHDOG_LAMBDA_ENV_NOT_UPDATED")
        # The watchdog must remain scheduled after the derived CFN changes.
        wr_after=ev.describe_rule(Name=watchdog_rule_name)
        require(wr_after.get("State")=="ENABLED" and
                wr_after.get("ScheduleExpression")=="rate(1 hour)",
                "POST_UPDATE_WATCHDOG_NOT_ENABLED")
        after=ev.list_targets_by_rule(Rule=watchdog_rule_name).get("Targets",[])
        require(len(after)==1 and after[0].get("Id")=="SessionWatchdog"
                and after[0].get("Arn")==watch_fn_arn,
                "POST_UPDATE_WATCHDOG_TARGET_CHANGED")
        print("ST_MONITORING_REPAIRED:"+SESSION,flush=True)
    else:
        print("ST_MONITORING_ALREADY_CONFIGURED:"+SESSION,flush=True)
    # Guard is fixed by full commit and verified git object hash before execution.
    target=Path.home()/"stocklens_enable_st_paper_guarded_verified.py"
    with urllib.request.urlopen(GUARD_URL,timeout=30) as response:
        raw=response.read()
    gitblob=hashlib.sha1(b"blob "+str(len(raw)).encode()+bytes([0])+raw).hexdigest()
    require(gitblob==GUARD_BLOB,"PINNED_GUARD_CHECKSUM_MISMATCH")
    target.write_bytes(raw)
    print("STARTING_ST_ONLY_GUARDED_PAPER_ENABLEMENT",flush=True)
    result=subprocess.run([sys.executable,str(target),"--apply"],check=False)
    require(result.returncode==0,"ST_PAPER_GUARD_REFUSED_ACTIVATION")
    print("ST_PAPER_MONITORING_AND_SCHEDULE_ENABLED:NO_PROD:NO_BROKER",flush=True)

if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("SAFE_STOP:"+str(exc),file=sys.stderr)
        sys.exit(2)

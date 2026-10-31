#!/usr/bin/env python3
"""One-time, fail-closed enablement of *ST-only* scheduled Paper after Genesis.

No PROD, broker, CloudFormation, S3 or Lambda writes. The only mutation,
when explicitly --apply, is EventBridge EnableRule for ST Paper-only.
Refuses to enable without complete read-only prerequisite evidence.
"""
import argparse, json, sys
from datetime import datetime, timezone

REGION="eu-central-1"
ACCOUNT="634740393398"
ST="stocklens-st"
PROD="stocklens-prod"
BUCKET="stocklens-st-candidatedata-6jj7i9fxjmfr"
GENESIS="2026-10-30"
BOOK="NEW_AWS_INDEPENDENT_STAGING_BOOK"
EXPECTED_CRON="cron(20 3 ? * TUE-SAT *)"

def ensure(ok, message):
    if not ok: raise RuntimeError(message)

def main():
    import boto3
    p=argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true", help="enable only the validated ST Paper-only EventBridge rule")
    a=p.parse_args()
    session=boto3.session.Session(region_name=REGION)
    sts=session.client("sts")
    cf=session.client("cloudformation")
    ev=session.client("events")
    lam=session.client("lambda")
    s3=session.client("s3")
    sns=session.client("sns")
    cw=session.client("cloudwatch")
    ensure(sts.get_caller_identity()["Account"]==ACCOUNT,"WRONG_AWS_ACCOUNT")
    def stack(name):
        z=cf.describe_stacks(StackName=name)["Stacks"]
        ensure(len(z)==1 and z[0]["StackStatus"] in ("CREATE_COMPLETE","UPDATE_COMPLETE"),"STACK_UNSTABLE:"+name)
        return ({v["OutputKey"]:v["OutputValue"] for v in z[0].get("Outputs",[])},
                {v["ParameterKey"]:v.get("ParameterValue","") for v in z[0].get("Parameters",[])})
    st, stp=stack(ST)
    prod, _=stack(PROD)
    ensure(st["CandidateDataBucket"]==BUCKET and prod["CandidateDataBucket"]!=BUCKET,"BUCKET_ISOLATION_FAILED")
    paper_rule=st["CandidatePaperOnlyRuleName"]
    for outputs,key,required in [
        (st,"CandidateSignalOnlyRuleName","ENABLED"),
        (st,"CandidateOrchestratorRuleName","DISABLED"),
        (prod,"CandidateSignalOnlyRuleName","DISABLED"),
        (prod,"CandidatePaperOnlyRuleName","DISABLED"),
        (prod,"CandidateOrchestratorRuleName","DISABLED")]:
        ensure(ev.describe_rule(Name=outputs[key])["State"]==required,"UNSAFE_EVENT_RULE:"+key)
    rule=ev.describe_rule(Name=paper_rule)
    ensure(rule["State"] in ("DISABLED","ENABLED"),"UNKNOWN_PAPER_SCHEDULE_STATE")
    ensure(rule.get("ScheduleExpression")==EXPECTED_CRON,"PAPER_CRON_UNEXPECTED")
    ensure(stp.get("MonitoringStartSession")==GENESIS,"PAPER_WATCHDOG_MONITORING_START_MISSING")
    target=ev.list_targets_by_rule(Rule=paper_rule)["Targets"]
    paper_fn=st["CandidatePaperFunctionName"]
    expected_arn=lam.get_function_configuration(FunctionName=paper_fn)["FunctionArn"]
    ensure(len(target)==1 and target[0].get("Arn")==expected_arn,"UNEXPECTED_PAPER_RULE_TARGETS")
    event=target[0].get("Input")
    ensure(isinstance(event,str) and json.loads(event)=={"mode":"STAGING_PAPER_SCHEDULED"},"UNEXPECTED_SCHEDULED_EVENT")
    cf_p=lam.get_function_configuration(FunctionName=paper_fn)
    cf_pf=lam.get_function_configuration(FunctionName=st["CandidatePaperPreflightFunctionName"])
    ensure(cf_p.get("State")=="Active" and cf_p.get("LastUpdateStatus")=="Successful","PAPER_LAMBDA_NOT_READY")
    ensure(cf_p.get("CodeSha256")==cf_pf.get("CodeSha256"),"PAPER_PREFLIGHT_ARTIFACT_DIFFER")
    ensure(cf_p.get("Environment",{}).get("Variables",{}).get("STOCKLENS_DATA_BUCKET")==BUCKET,"PAPER_BUCKET_WRONG")
    # Verify durable genesis plus final completed-session chain using the dedicated read-only readiness mode.
    resp=lam.invoke(FunctionName=paper_fn,InvocationType="RequestResponse",
        Payload=json.dumps({"mode":"STAGING_PAPER_SCHEDULE_READINESS","expected_session":GENESIS,"bootstrap":False}).encode())
    data=json.loads(resp["Payload"].read())
    ensure(not resp.get("FunctionError"),"READINESS_LAMBDA_ERROR:"+str(data)[:250])
    ensure(data.get("status")=="STAGING_PAPER_SCHEDULE_READINESS_PASS_READ_ONLY"
           and data.get("genesis_session")==GENESIS and data.get("chain_sessions")==1
           and data.get("continuity_status") in ("ON_TIME_QUALIFIED","LATE_WITH_CONTEMPORANEOUS_EVIDENCE")
           and data.get("broker_actions") is False and data.get("paper_data_written") is False,
           "READINESS_CHAIN_INCOMPLETE")
    ensure(data.get("broker_orders") is False and data.get("broker_fills") is False,"BROKER_FLAG_INVALID")
    # Independently confirm genesis exists in the isolated bucket with versioning.
    key=f"paper/book/{BOOK}/genesis.json"
    meta=s3.head_object(Bucket=BUCKET,Key=key)
    ensure(meta.get("VersionId") not in (None,"null"),"GENESIS_NOT_VERSIONED")
    topic=st["CandidateAlertsTopic"]
    subs=sns.list_subscriptions_by_topic(TopicArn=topic)["Subscriptions"]
    ensure(any(x.get("Protocol")=="email" and x.get("SubscriptionArn") not in ("PendingConfirmation",None)
               for x in subs),"SNS_EMAIL_UNCONFIRMED")
    # Fail closed if CloudWatch alarm actions or alarm states cannot be inspected.
    alarms=cw.describe_alarms(AlarmNamePrefix=ST)["MetricAlarms"]
    ensure(alarms and all(x.get("ActionsEnabled") is True for x in alarms),"ST_ALARM_ACTIONS_NOT_ACTIVE")
    severe=[x["AlarmName"] for x in alarms if x.get("StateValue")=="ALARM"]
    ensure(not severe,"ST_ALARMS_ACTIVE:"+str(severe))
    summary={"state":"READINESS_PASS","genesis":GENESIS,"verified_chain_sessions":data["chain_sessions"],
             "paper_schedule_before":rule["State"],"paper_rule":paper_rule,
             "monitoring_start":stp["MonitoringStartSession"],"broker":False,"prod_changes":False}
    print(json.dumps(summary,indent=2))
    if not a.apply:
        print("READ_ONLY_PASS_RUN_WITH_--apply_TO_ENABLE_ST_PAPER_ONLY")
        return
    if rule["State"]=="ENABLED":
        print("ALREADY_ENABLED_NO_MUTATION")
        return
    ev.enable_rule(Name=paper_rule)
    ensure(ev.describe_rule(Name=paper_rule)["State"]=="ENABLED","ST_PAPER_ENABLE_VERIFY_FAILED")
    print("ST_PAPER_ONLY_ENABLED:PROD_DISABLED:NO_BROKER:NO_ORCHESTRATOR")
if __name__=="__main__":
    try: main()
    except Exception as e:
        print("ST_PAPER_SCHEDULE_BLOCKED:"+str(e))
        sys.exit(2)

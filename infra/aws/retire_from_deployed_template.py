#!/usr/bin/env python3
"""StockLens legacy AWS retirement. Uses live DEPLOYED CloudFormation YAML as base.

preview = read-only (except CloudFormation template syntax validation)
apply = create an inert change set, validate exact non-destructive updates,
        then require the operator's explicit typed approval before execution.
No broker orders, no staging modification, no DynamoDB deletion/backfill.
"""
import difflib
import json
import re
import sys
import time

import boto3
from botocore.exceptions import ClientError, WaiterError

REGION = "eu-central-1"
ACCOUNT = "634740393398"
LEGACY = "stocklens-paper"
STAGING = "stocklens-independent-staging"
RULES = ("NightlyRule", "PaperEvidenceSchedule", "WatchdogSchedule")
ALARMS = ("ErrorAlarm", "PaperEvidenceAlarm", "WatchdogErrorAlarm", "WatchdogHeartbeatAlarm")
CONFIRM = "RETIRE_OLD_STOCKLENS_PAPER_SCHEDULES"
ALLOWED = {**{k: {"State"} for k in RULES},
           **{k: {"AlarmActions"} for k in ALARMS}}
ALLOWED["WatchdogHeartbeatAlarm"].add("TreatMissingData")


def refuse(reason):
    raise SystemExit("REFUSE:" + str(reason))


def main():
    mode = sys.argv[1] if len(sys.argv) == 2 else "preview"
    if mode not in ("preview", "apply"):
        refuse("USAGE: python3 retire_stocklens_legacy.py preview|apply")
    session = boto3.Session(region_name=REGION)
    cfn = session.client("cloudformation")
    events = session.client("events")
    cw = session.client("cloudwatch")
    db = session.client("dynamodb")
    if session.client("sts").get_caller_identity()["Account"] != ACCOUNT:
        refuse("WRONG_ACCOUNT")
    old = cfn.describe_stacks(StackName=LEGACY)["Stacks"][0]
    if old["StackStatus"] not in ("CREATE_COMPLETE", "UPDATE_COMPLETE"):
        refuse("LEGACY_STACK_NOT_STABLE:" + old["StackStatus"])
    params = old.get("Parameters", [])
    if {p["ParameterKey"] for p in params} != {"AlertEmail"}:
        refuse("UNEXPECTED_LEGACY_PARAMETERS")
    outputs = {o["OutputKey"]: o["OutputValue"] for o in old.get("Outputs", [])}
    table = outputs.get("TableName")
    if not table or db.describe_table(TableName=table)["Table"]["TableStatus"] != "ACTIVE":
        refuse("LEGACY_DYNAMODB_NOT_ACTIVE")
    new = cfn.describe_stacks(StackName=STAGING)["Stacks"][0]
    new_outputs = {o["OutputKey"]: o["OutputValue"] for o in new.get("Outputs", [])}
    sig = new_outputs.get("CandidateSignalOnlyRuleName")
    orch = new_outputs.get("CandidateOrchestratorRuleName")
    if not sig or not orch:
        refuse("STAGING_OUTPUTS_MISSING")
    signal_info = events.describe_rule(Name=sig)
    if (signal_info["State"] != "ENABLED"
            or signal_info["ScheduleExpression"] != "cron(30 2 ? * TUE-SAT *)"):
        refuse("STAGING_SIGNAL_NOT_ACTIVE")
    if events.describe_rule(Name=orch)["State"] != "DISABLED":
        refuse("STAGING_ORCHESTRATOR_NOT_DISABLED")

    def resource(name, expected_type):
        info = cfn.describe_stack_resource(StackName=LEGACY, LogicalResourceId=name)["StackResourceDetail"]
        if info["ResourceType"] != expected_type:
            refuse("UNEXPECTED_RESOURCE_TYPE:" + name)
        return info["PhysicalResourceId"]

    rule_ids = {r: resource(r, "AWS::Events::Rule") for r in RULES}
    alarm_ids = {a: resource(a, "AWS::CloudWatch::Alarm") for a in ALARMS}
    topic = resource("PaperAlertTopic", "AWS::SNS::Topic")
    for name, rid in rule_ids.items():
        if events.describe_rule(Name=rid)["State"] != "ENABLED":
            refuse("LEGACY_RULE_NOT_ENABLED:" + name)
    for name, rid in alarm_ids.items():
        alarms = cw.describe_alarms(AlarmNames=[rid])["MetricAlarms"]
        if len(alarms) != 1 or alarms[0].get("AlarmActions", []) != [topic]:
            refuse("LEGACY_ALARM_NOTIFICATIONS_UNEXPECTED:" + name)
    heart = cw.describe_alarms(AlarmNames=[alarm_ids["WatchdogHeartbeatAlarm"]])["MetricAlarms"][0]
    if heart.get("TreatMissingData") != "breaching":
        refuse("LEGACY_HEARTBEAT_UNEXPECTED_MISSING_DATA_POLICY")

    body = cfn.get_template(StackName=LEGACY, TemplateStage="Original")["TemplateBody"]
    if not isinstance(body, str) or "\nResources:" not in ("\n" + body):
        refuse("ORIGINAL_DEPLOYED_TEMPLATE_NOT_YAML")
    patched = body
    for name in (*RULES, *ALARMS):
        start = re.search(r"(?m)^  " + re.escape(name) + r":[ \t]*$", patched)
        if not start:
            refuse("MISSING_YAML_RESOURCE_BLOCK:" + name)
        tail = patched[start.end():]
        ending = re.search(r"(?m)^  [A-Za-z][A-Za-z0-9]*:[ \t]*$|^Outputs:[ \t]*$", tail)
        end = start.end() + (ending.start() if ending else len(tail))
        section = patched[start.end():end]
        if name in RULES:
            section, count = re.subn(
                r"(?m)^([ ]{6}State:[ \t]*)ENABLED[ \t]*$",
                r"\g<1>DISABLED", section)
        else:
            section, count = re.subn(
                r"(?m)^([ ]{6}AlarmActions:[ \t]*)!If[ \t]*\[EmailAlertsConfigured,[^\n]*$",
                r"\g<1>[]", section)
            if name == "WatchdogHeartbeatAlarm" and count == 1:
                section, heartbeat_count = re.subn(
                    r"(?m)^([ ]{6}TreatMissingData:[ \t]*)breaching[ \t]*$",
                    r"\g<1>notBreaching", section)
                if heartbeat_count != 1:
                    refuse("HEARTBEAT_POLICY_NOT_PATCHED")
        if count != 1:
            refuse("EXPECTED_EXACTLY_ONE_PROPERTY_PATCH:" + name + ":" + str(count))
        patched = patched[:start.end()] + section + patched[end:]

    # Syntax-only AWS validation: does NOT update the CloudFormation stack.
    cfn.validate_template(TemplateBody=patched)
    delta = list(difflib.unified_diff(body.splitlines(), patched.splitlines(),
                                      fromfile="deployed", tofile="retirement", lineterm=""))
    print("\n".join(delta))
    print("PATCH_VALIDATED: 3 EventBridge rules and 4 CloudWatch alarms")
    print("STAGING_SIGNAL_ACTIVE; STAGING_ORCHESTRATOR_DISABLED; DYNAMODB_RETAINED")
    if mode == "preview":
        print("PREVIEW_COMPLETE: READ_ONLY; no change set created; no AWS resources updated")
        return

    # CFN change set is inert until execute_change_set is explicitly requested.
    change_set = "stocklens-retire-deployed-" + time.strftime("%Y%m%d%H%M%S", time.gmtime())
    cfn.create_change_set(StackName=LEGACY, ChangeSetName=change_set,
                          ChangeSetType="UPDATE", TemplateBody=patched,
                          Parameters=[{"ParameterKey": "AlertEmail", "UsePreviousValue": True}],
                          Capabilities=["CAPABILITY_IAM"])
    print("INERT_CHANGE_SET_CREATED:" + change_set, flush=True)
    try:
        cfn.get_waiter("change_set_create_complete").wait(
            StackName=LEGACY, ChangeSetName=change_set)
    except WaiterError as exc:
        refuse("CHANGE_SET_NOT_READY_NO_EXECUTION:" + str(exc))
    changeset = cfn.describe_change_set(StackName=LEGACY, ChangeSetName=change_set)
    print("CHANGE_SET_RESOURCES:")
    for c in changeset.get("Changes", []):
        r = c.get("ResourceChange", {})
        print(" ", r.get("LogicalResourceId"), r.get("Action"), r.get("Replacement"),
              [(d.get("Target", {}).get("Name"), d.get("Target", {}).get("RequiresRecreation"))
               for d in r.get("Details", [])])
    if changeset.get("Status") != "CREATE_COMPLETE" or changeset.get("ExecutionStatus") != "AVAILABLE":
        refuse("CHANGESET_NOT_AVAILABLE")
    changes = changeset.get("Changes", [])
    if len(changes) != 7:
        refuse("EXPECTED_EXACTLY_7_NONDESTRUCTIVE_CHANGES_GOT:" + str(len(changes)))
    seen = set()
    for entry in changes:
        c = entry.get("ResourceChange", {})
        name = c.get("LogicalResourceId")
        if name not in ALLOWED or name in seen:
            refuse("UNEXPECTED_OR_DUPLICATE_CHANGE:" + str(name))
        seen.add(name)
        expected_type = "AWS::Events::Rule" if name in RULES else "AWS::CloudWatch::Alarm"
        if (c.get("Action") != "Modify"
                or c.get("Replacement") not in ("False", False)
                or c.get("ResourceType") != expected_type
                or set(c.get("Scope", [])) != {"Properties"}):
            refuse("UNEXPECTED_RESOURCE_CHANGE:" + name)
        details = c.get("Details") or []
        properties = set()
        if not details:
            refuse("NO_CHANGE_DETAILS:" + name)
        for detail in details:
            target = detail.get("Target", {})
            prop = target.get("Name")
            if (target.get("Attribute") != "Properties" or prop not in ALLOWED[name]
                    or target.get("RequiresRecreation") != "Never"):
                refuse("UNEXPECTED_PROPERTY_OR_REPLACEMENT:" + name + ":" + str(prop))
            properties.add(prop)
        if properties != ALLOWED[name]:
            refuse("MISSING_EXPECTED_PROPERTY_CHANGE:" + name + ":" + str(properties))

    print("EXACTLY_7_NONDESTRUCTIVE_CHANGES_VERIFIED; no DynamoDB/IAM/SNS/Lambda modifications")
    answer = input("Type " + CONFIRM + " to execute reviewed changes: ").strip()
    if answer != CONFIRM:
        refuse("NOT_APPROVED; inert change set remains: " + change_set)
    cfn.execute_change_set(StackName=LEGACY, ChangeSetName=change_set)
    cfn.get_waiter("stack_update_complete").wait(StackName=LEGACY)
    for name, rid in rule_ids.items():
        if events.describe_rule(Name=rid)["State"] != "DISABLED":
            refuse("POST_DEPLOY_RULE_STATE:" + name)
    for name, rid in alarm_ids.items():
        m = cw.describe_alarms(AlarmNames=[rid])["MetricAlarms"]
        if len(m) != 1 or m[0].get("AlarmActions"):
            refuse("POST_DEPLOY_ALARM_ACTIONS:" + name)
    m = cw.describe_alarms(AlarmNames=[alarm_ids["WatchdogHeartbeatAlarm"]])["MetricAlarms"]
    if m[0].get("TreatMissingData") != "notBreaching":
        refuse("POST_DEPLOY_HEARTBEAT_POLICY")
    if events.describe_rule(Name=sig)["State"] != "ENABLED":
        refuse("POST_DEPLOY_STAGING_SIGNAL")
    if db.describe_table(TableName=table)["Table"]["TableStatus"] != "ACTIVE":
        refuse("POST_DEPLOY_DYNAMODB")
    print("LEGACY_RETIREMENT_VERIFIED:3_schedules_off:4_alarm_actions_off:table_retained:staging_signal_on")
    print("NO_BROKER_ACTIONS; NEW_PAPER_REMAINS_DISABLED")


if __name__ == "__main__":
    try:
        main()
    except ClientError as exc:
        refuse("AWS_API_ERROR:" + str(exc.response.get("Error", {}).get("Code")) + ":" +
               str(exc.response.get("Error", {}).get("Message")))

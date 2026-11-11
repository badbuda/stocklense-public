#!/usr/bin/env python3
"""Read-only ST/PROD nightly acceptance. No S3 writes, broker or EventBridge mutations.

A passing Shadow workflow does not certify AWS. This command reads the deployed
ST signal, checks isolated scheduler states, and asks the already-deployed Paper
Lambda ONLY for its documented read-only continuity attestation. It verifies
the attested Paper byte hash against the versioned object in the ST bucket.
Fail closed on permissions, stale sessions, missing receipts, alarms, or drift.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import re
import sys

REGION = "eu-central-1"
ACCOUNT = "634740393398"
ST = "stocklens-st"
PROD = "stocklens-prod"
BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
PROD_BUCKET = "stocklens-prod-candidatedata-c3yge4ymwb7u"
BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK"
GENESIS = "2026-10-30"
# ST guarded release (2026-11-10) uses pre-open retries and delayed Paper.
# PROD must remain disabled with its original CloudFormation cron definitions.
SIGNAL_CRON = "cron(30 5,8,11,12 ? * TUE-SAT *)"
PAPER_CRON = "cron(0 13 ? * TUE-SAT *)"
ORCHESTRATOR_CRON = "cron(10 0 ? * TUE-SAT *)"
PROD_SIGNAL_CRON = "cron(30 2 ? * TUE-SAT *)"
PROD_PAPER_CRON = "cron(20 3 ? * TUE-SAT *)"
SHA = re.compile(r"^[0-9a-f]{64}$")
CONTINUITY = {"ON_TIME_QUALIFIED", "LATE_WITH_CONTEMPORANEOUS_EVIDENCE"}


def require(condition: bool, reason: str):
    if not condition:
        raise RuntimeError(reason)


def stack(cf, name):
    results = cf.describe_stacks(StackName=name)["Stacks"]
    require(len(results) == 1 and results[0]["StackStatus"] in
            ("CREATE_COMPLETE", "UPDATE_COMPLETE"), "UNSTABLE_STACK:" + name)
    return {x["OutputKey"]: x["OutputValue"] for x in results[0].get("Outputs", [])}


def read_versioned_json(s3, key, *, version=None):
    opts = {"Bucket": BUCKET, "Key": key}
    if version is not None:
        opts["VersionId"] = version
    obj = s3.get_object(**opts)
    require(obj.get("VersionId") not in (None, "", "null"), "UNVERSIONED_S3:" + key)
    require(obj.get("ContentLength", -1) in range(0, 2_000_001), "OVERSIZED_S3:" + key)
    raw = obj["Body"].read(2_000_001)
    require(len(raw) == obj["ContentLength"], "S3_LENGTH_MISMATCH:" + key)
    return json.loads(raw), obj["VersionId"], hashlib.sha256(raw).hexdigest()


def receipt_key_for_version(s3, version):
    # The deployed key layout is not a public API contract. Find the exact
    # immutable S3 version rather than infer a receipt key or fabricate fills.
    prefix = "paper/"
    args = {"Bucket": BUCKET, "Prefix": prefix, "MaxKeys": 1000}
    matches = []
    for page in range(5):
        result = s3.list_object_versions(**args)
        matches += [(x["Key"], x["VersionId"]) for x in result.get("Versions", [])
                    if x.get("VersionId") == version]
        if not result.get("IsTruncated"):
            break
        require(bool(result.get("NextKeyMarker")) and bool(result.get("NextVersionIdMarker")),
                "PAPER_S3_VERSION_PAGINATION_UNVERIFIED")
        args["KeyMarker"] = result["NextKeyMarker"]
        args["VersionIdMarker"] = result["NextVersionIdMarker"]
    else:
        raise RuntimeError("PAPER_S3_VERSION_SEARCH_INCOMPLETE")
    require(len(matches) == 1, "PAPER_VERSION_NOT_UNIQUELY_FOUND")
    return matches[0][0]


def audit(services, session):
    require(date.fromisoformat(session).isoformat() == session, "BAD_ISO_SESSION")
    sts, cf, ev, s3, lam, cw, sns = (
        services[x] for x in ("sts", "cloudformation", "events", "s3", "lambda", "cloudwatch", "sns")
    )
    # Account is checked before reading *any* account resource.
    require(sts.get_caller_identity().get("Account") == ACCOUNT, "WRONG_AWS_ACCOUNT")
    st, prod = stack(cf, ST), stack(cf, PROD)
    require(st.get("CandidateDataBucket") == BUCKET and
            prod.get("CandidateDataBucket") == PROD_BUCKET and BUCKET != PROD_BUCKET,
            "ST_PROD_BUCKET_MISMATCH")
    require(s3.get_bucket_versioning(Bucket=BUCKET).get("Status") == "Enabled",
            "ST_S3_VERSIONING_OFF")
    expected_st = {"CandidateSignalOnlyRuleName": SIGNAL_CRON,
                   "CandidatePaperOnlyRuleName": PAPER_CRON,
                   "CandidateOrchestratorRuleName": ORCHESTRATOR_CRON}
    expected_prod = {"CandidateSignalOnlyRuleName": PROD_SIGNAL_CRON,
                     "CandidatePaperOnlyRuleName": PROD_PAPER_CRON,
                     "CandidateOrchestratorRuleName": ORCHESTRATOR_CRON}
    state = {}
    for label, outputs, expected in (("ST", st, expected_st),
                                     ("PROD", prod, expected_prod)):
        for key, cron in expected.items():
            rule = ev.describe_rule(Name=outputs[key])
            require(rule.get("ScheduleExpression") == cron, "WRONG_CRON:" + label + ":" + key)
            value = rule.get("State")
            state[label + ":" + key] = value
            require(value in ("ENABLED", "DISABLED"), "UNKNOWN_RULE_STATE")
            if label == "PROD":
                require(value == "DISABLED", "PROD_RULE_ACTIVE:" + key)
    require(state["ST:CandidateSignalOnlyRuleName"] == "ENABLED" and
            state["ST:CandidateOrchestratorRuleName"] == "DISABLED",
            "ST_SIGNAL_OR_ORCHESTRATOR_UNSAFE")
    topic = st["CandidateAlertsTopic"]
    subscriptions = sns.list_subscriptions_by_topic(TopicArn=topic).get("Subscriptions", [])
    require(any(x.get("Protocol") == "email" and
                x.get("SubscriptionArn") not in (None, "PendingConfirmation")
                for x in subscriptions), "ST_SNS_EMAIL_UNCONFIRMED")
    alarms = cw.describe_alarms(AlarmNamePrefix="stocklens-st").get("MetricAlarms", [])
    require(bool(alarms), "NO_ST_ALARMS")
    unknown = [x["AlarmName"] for x in alarms if x.get("StateValue") != "OK"]
    require(not unknown, "ST_ALARM_OR_INSUFFICIENT_DATA:" + ",".join(unknown))
    require(all(x.get("ActionsEnabled") is True and topic in x.get("AlarmActions", [])
                for x in alarms), "ST_ALARM_EMAIL_ACTIONS_UNVERIFIED")
    signal, signal_version, signal_sha = read_versioned_json(s3, f"signals/{session}.json")
    require(signal.get("mode") == "SHADOW_ONLY_NO_BROKER_ACTIONS" and
            signal.get("latest", {}).get("asof_date") == session and
            signal.get("execution_plan", {}).get("broker_actions_enabled") is False,
            "ST_SIGNAL_MISMATCH_OR_UNSAFE")
    report = {
        "session": session,
        "source": "AWS_ST_AUTHENTICATED_VERSIONED_READBACK",
        "st_signal": "VERIFIED_VERSIONED_S3",
        "signal_version": signal_version,
        "signal_sha256": signal_sha,
        "st_paper_schedule": state["ST:CandidatePaperOnlyRuleName"],
        "prod_schedules": "ALL_DISABLED",
        "st_alarms": "ALL_OK",
        "broker_orders": False,
        "aws_mutations": False,
        "paper_chain": "NOT_YET_PROVEN",
    }
    require(state["ST:CandidatePaperOnlyRuleName"] == "ENABLED",
            "ST_RECURRING_PAPER_SCHEDULE_DISABLED")
    config = lam.get_function_configuration(FunctionName=st["CandidatePaperFunctionName"])
    signal_config = lam.get_function_configuration(FunctionName=st["CandidateFunctionName"])
    require(config.get("State") == "Active" and
            config.get("LastUpdateStatus") == "Successful" and
            config.get("Environment", {}).get("Variables", {}).get("STOCKLENS_DATA_BUCKET") == BUCKET,
            "ST_PAPER_FUNCTION_NOT_READY")
    require(signal_config.get("State") == "Active" and
            signal_config.get("LastUpdateStatus") == "Successful" and
            signal_config.get("Environment", {}).get("Variables", {}).get("STOCKLENS_DATA_BUCKET") == BUCKET,
            "ST_SIGNAL_FUNCTION_NOT_READY")
    for key, cfg in (("CandidatePaperOnlyRuleName", config),
                     ("CandidateSignalOnlyRuleName", signal_config)):
        targets = ev.list_targets_by_rule(Rule=st[key]).get("Targets", [])
        require(len(targets) == 1 and targets[0].get("Arn") == cfg.get("FunctionArn"),
                "ST_SCHEDULE_TARGET_MISMATCH:" + key)
    event = {"mode": "STAGING_PAPER_SCHEDULE_READINESS",
             "expected_session": session, "bootstrap": False}
    response = lam.invoke(FunctionName=st["CandidatePaperFunctionName"],
                          InvocationType="RequestResponse",
                          Payload=json.dumps(event).encode("utf-8"))
    require(response.get("StatusCode") == 200 and not response.get("FunctionError"),
            "PAPER_READ_ONLY_READINESS_LAMBDA_ERROR")
    payload = response["Payload"].read(250_001)
    require(len(payload) <= 250_000, "OVERSIZED_PAPER_READINESS")
    result = json.loads(payload)
    require(result.get("status") == "STAGING_PAPER_SCHEDULE_READINESS_PASS_READ_ONLY" and
            result.get("session") == session and result.get("genesis_session") == GENESIS and
            type(result.get("chain_sessions")) is int and result["chain_sessions"] >= 1 and
            result.get("continuity_status") in CONTINUITY and
            result.get("broker_actions") is False and
            result.get("paper_data_written") is False and
            result.get("broker_orders") is False and result.get("broker_fills") is False,
            "PAPER_READINESS_NOT_QUALIFIED")
    paper_version, paper_sha = result.get("paper_version_id"), result.get("paper_sha256")
    require(isinstance(paper_version, str) and len(paper_version) > 1 and
            isinstance(paper_sha, str) and SHA.fullmatch(paper_sha),
            "PAPER_RECEIPT_IDENTITY_MISSING")
    key = receipt_key_for_version(s3, paper_version)
    record, verified_version, verified_sha = read_versioned_json(s3, key, version=paper_version)
    require(verified_version == paper_version and verified_sha == paper_sha,
            "PAPER_S3_RECEIPT_HASH_MISMATCH")
    # Do not turn modeled receipts into claimed broker executions.
    report["paper_chain"] = "ATTESTED_VERSIONED_MODELED_PAPER_NOT_BROKER"
    report["paper_sessions"] = result["chain_sessions"]
    report["paper_session"] = session
    report["paper_receipt_sha256"] = verified_sha
    report["paper_receipt_key"] = key
    report["paper_continuity"] = result["continuity_status"]
    report["status"] = "ST_READ_ONLY_ACCEPTANCE_PASS_MODELED_ONLY"
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--session", required=True, help="completed XNYS session, YYYY-MM-DD")
    args = p.parse_args()
    try:
        import boto3
        client = boto3.session.Session(region_name=REGION)
        services = {name: client.client(name) for name in
                    ("sts", "cloudformation", "events", "s3", "lambda", "cloudwatch", "sns")}
        report = audit(services, args.session)
    except Exception as exc:
        report = {"status": "ST_READ_ONLY_ACCEPTANCE_BLOCKED",
                  "reason": str(exc)[:350], "session": args.session,
                  "aws_mutations": False, "broker_orders": False}
    print(json.dumps(report, sort_keys=True, ensure_ascii=False, indent=2))
    return 0 if report["status"] == "ST_READ_ONLY_ACCEPTANCE_PASS_MODELED_ONLY" else 2


if __name__ == "__main__":
    sys.exit(main())

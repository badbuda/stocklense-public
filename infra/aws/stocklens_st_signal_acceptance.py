#!/usr/bin/env python3
"""Independent read-only ST nightly Signal + hourly watchdog acceptance.

Evaluates real deployed AWS objects, EventBridge, SNS and CloudWatch. Before
the next scheduled session's one-hour grace deadline, absence is PENDING,
not a manufactured missing signal. After deadline, a missing or corrupt
Signal is BLOCKED. A pass never certifies Paper or real brokerage fills.
No mutating AWS calls, Lambda invokes, deploys or data backfills.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import sys

ACCOUNT = "634740393398"
REGION = "eu-central-1"
ST = "stocklens-st"
PROD = "stocklens-prod"
BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
PROD_BUCKET = "stocklens-prod-candidatedata-c3yge4ymwb7u"
SIGNAL_CRON = "cron(30 2 ? * TUE-SAT *)"
WATCHDOG_CRON = "rate(1 hour)"
ACTIVATION = "monitoring/signal-only-activation.json"
ALARM_IDS = (
    "CandidateSignalErrorsAlarm",
    "CandidateSessionWatchdogErrorsAlarm",
    "MissingOrLateScheduledSignalsAlarm",
    "MissedSessionsAlarm",
    "BookHaltedAlarm",
    "SchedulerStateMismatchAlarm",
    "InvalidContinuityRecordAlarm",
    "WatchdogConfigurationErrorAlarm",
    "WatchdogFailClosedAlarm",
    "WatchdogHeartbeatDeadmanAlarm",
)


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def outputs(cf, name):
    records = cf.describe_stacks(StackName=name)["Stacks"]
    require(len(records) == 1 and records[0]["StackStatus"] in
            ("CREATE_COMPLETE", "UPDATE_COMPLETE"), "STACK_NOT_STABLE:" + name)
    return {v["OutputKey"]: v["OutputValue"] for v in records[0].get("Outputs", [])}


def rule(events, name, expected_state, expected_schedule):
    data = events.describe_rule(Name=name)
    require(data.get("State") == expected_state, "UNSAFE_EVENTBRIDGE_STATE:" + name)
    require(data.get("ScheduleExpression") == expected_schedule, "UNEXPECTED_CRON:" + name)
    return data


def read_s3(s3, bucket, key, *, max_bytes=4_000_000):
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code in ("NoSuchKey", "404", "NotFound"):
            return None
        raise RuntimeError("S3_READ_FAILED:" + key + ":" + str(code or type(exc).__name__)) from exc
    require(obj.get("VersionId") not in (None, "null", ""),
            "UNVERSIONED_S3_OBJECT:" + key)
    require(obj.get("LastModified") is not None and
            obj["LastModified"].tzinfo is not None, "S3_TIMESTAMP_MISSING:" + key)
    length = obj.get("ContentLength")
    require(length is not None and 0 <= length <= max_bytes,
            "S3_SIZE_INVALID:" + key)
    raw = obj["Body"].read(max_bytes + 1)
    require(len(raw) == length, "S3_OBJECT_LENGTH_MISMATCH:" + key)
    return {"data": raw, "sha256": hashlib.sha256(raw).hexdigest(),
            "version": obj["VersionId"], "saved_at": obj["LastModified"]}


def validate_signal(s3, session, now):
    market_key = f"market/qqq/{session}.csv"
    manifest_key = f"manifests/qqq/{session}.json"
    signal_key = f"signals/{session}.json"
    sig = read_s3(s3, BUCKET, signal_key)
    if sig is None:
        return None
    market = read_s3(s3, BUCKET, market_key)
    manifest = read_s3(s3, BUCKET, manifest_key)
    require(market is not None and manifest is not None, "UNBOUND_SIGNAL_MISSING_SOURCE")
    signal, m = json.loads(sig["data"]), json.loads(manifest["data"])
    market_audit = m.get("audit", {})
    signal_audit = signal.get("data_audit", {})
    require(signal.get("mode") == "SHADOW_ONLY_NO_BROKER_ACTIONS" and
            signal.get("latest", {}).get("asof_date") == session and
            signal.get("execution_plan", {}).get("broker_actions_enabled") is False and
            signal_audit.get("source_sha256") == market["sha256"] and
            m.get("status") == "VERIFIED" and
            m.get("provider") == "YFINANCE_QQQ_AUTO_ADJUSTED" and
            m.get("data_type") == "QQQ_ADJUSTED_DAILY" and
            m.get("input_key") == market_key and
            m.get("input_version_id") == market["version"] and
            m.get("sha256") == market["sha256"] and
            market_audit.get("csv_sha256") == market["sha256"] and
            market_audit.get("last_session") == session and
            market_audit.get("source_path") == "stocklens.data.load_qqq_history" and
            market_audit.get("data_integrity_status") ==
                "FROZEN_YFINANCE_SOURCE_VERIFIED_NOT_INDEPENDENT_VENDOR" and
            market_audit.get("reference_feature_window_sha256") ==
                signal_audit.get("feature_window_sha256") and
            bool(signal_audit.get("feature_window_sha256")),
            "SIGNAL_SOURCE_HASH_DATE_OR_FROZEN_FEATURE_MISMATCH")
    require(sig["saved_at"] <= now + timedelta(minutes=1), "SIGNAL_SAVED_IN_FUTURE")
    # A manually pre-created signal is not evidence that the nightly
    # EventBridge scheduled invocation happened. Preserve immutable
    # content, but fail scheduled acceptance instead of back-dating it.
    scheduled = datetime.combine(
        date.fromisoformat(session) + timedelta(days=1),
        time(2, 30), tzinfo=timezone.utc)
    require(sig["saved_at"] >= scheduled,
            "SIGNAL_ARCHIVED_BEFORE_SCHEDULE_NOT_AUTOMATIC_PROOF")
    return {"status": "SHA_VERSION_CHAIN_VERIFIED",
            "session": session,
            "signal_saved_at_utc": sig["saved_at"].isoformat(),
            "signal_version_id": sig["version"],
            "market_sha256": market["sha256"],
            "signal_sha256": sig["sha256"],
            "level": signal["latest"].get("level"),
            "target_leverage": signal["latest"].get("target_leverage"),
            "action": signal.get("action"),
            "broker_fills": False}


def check(services, session: str, *, now=None):
    now = now or datetime.now(timezone.utc)
    require(now.tzinfo is not None, "CLOCK_NAIVE")
    now = now.astimezone(timezone.utc)
    target = date.fromisoformat(session)
    require(target.isoformat() == session, "INVALID_SESSION_DATE")
    # EventBridge runs at 02:30 UTC the NEXT calendar day after the XNYS
    # completed session, with a 60-minute grace period.
    due = datetime.combine(target + timedelta(days=1), time(3, 30), tzinfo=timezone.utc)
    sts, cf, events, s3, sns, cw, lam = (
        services[x] for x in ("sts", "cloudformation", "events", "s3", "sns", "cloudwatch", "lambda")
    )
    require(sts.get_caller_identity()["Account"] == ACCOUNT, "WRONG_AWS_ACCOUNT_NO_FURTHER_READ")
    st, prod = outputs(cf, ST), outputs(cf, PROD)
    require(st.get("CandidateDataBucket") == BUCKET and
            prod.get("CandidateDataBucket") == PROD_BUCKET and
            BUCKET != PROD_BUCKET, "ST_PROD_BUCKET_ISOLATION_FAILED")
    signal_rule = st["CandidateSignalOnlyRuleName"]
    paper_rule = st["CandidatePaperOnlyRuleName"]
    orchestrator_rule = st["CandidateOrchestratorRuleName"]
    rule(events, signal_rule, "ENABLED", SIGNAL_CRON)
    rule(events, paper_rule, "DISABLED", "cron(20 3 ? * TUE-SAT *)")
    rule(events, orchestrator_rule, "DISABLED", "cron(10 0 ? * TUE-SAT *)")
    for key in ("CandidateSignalOnlyRuleName", "CandidatePaperOnlyRuleName",
                "CandidateOrchestratorRuleName"):
        expected = {"CandidateSignalOnlyRuleName": SIGNAL_CRON,
                    "CandidatePaperOnlyRuleName": "cron(20 3 ? * TUE-SAT *)",
                    "CandidateOrchestratorRuleName": "cron(10 0 ? * TUE-SAT *)"}[key]
        rule(events, prod[key], "DISABLED", expected)

    signal_fn = st["CandidateFunctionName"]
    fn = lam.get_function_configuration(FunctionName=signal_fn)
    require(fn.get("State") == "Active" and
            fn.get("LastUpdateStatus") == "Successful" and
            fn.get("Handler") == "infra.aws.independent_pipeline.handler" and
            fn.get("Environment", {}).get("Variables", {}).get("STOCKLENS_DATA_BUCKET") == BUCKET,
            "ST_SIGNAL_LAMBDA_UNREADY")
    targets = events.list_targets_by_rule(Rule=signal_rule).get("Targets", [])
    require(len(targets) == 1 and targets[0].get("Arn") == fn.get("FunctionArn"),
            "ST_SIGNAL_EVENTBRIDGE_WRONG_TARGET")

    marker = read_s3(s3, BUCKET, ACTIVATION, max_bytes=4096)
    require(marker is not None and
            json.loads(marker["data"]) == {"schema": "STOCKLENS_STAGING_SIGNAL_MONITOR_V1"},
            "ST_SIGNAL_ACTIVATION_MARKER_MISSING_OR_INVALID")
    require(marker["saved_at"] <= now, "ACTIVATION_IN_FUTURE")
    require(marker["saved_at"] <
            datetime.combine(target + timedelta(days=1), time(2, 30), tzinfo=timezone.utc),
            "SESSION_SCHEDULE_PREDATES_ACTIVATION")

    physical = cf.describe_stack_resource(
        StackName=ST, LogicalResourceId="CandidateSessionWatchdogSchedule"
    )["StackResourceDetail"]["PhysicalResourceId"]
    rule(events, physical, "ENABLED", WATCHDOG_CRON)
    watchdog_fn = st["CandidateSessionWatchdogFunctionName"]
    watchdog = lam.get_function_configuration(FunctionName=watchdog_fn)
    require(watchdog.get("State") == "Active" and
            watchdog.get("LastUpdateStatus") == "Successful" and
            watchdog.get("Environment", {}).get("Variables", {}).get("STOCKLENS_DATA_BUCKET") == BUCKET,
            "ST_WATCHDOG_LAMBDA_UNREADY")
    watchdog_targets = events.list_targets_by_rule(Rule=physical).get("Targets", [])
    require(len(watchdog_targets) == 1 and
            watchdog_targets[0].get("Arn") == watchdog.get("FunctionArn"),
            "ST_WATCHDOG_WRONG_TARGET")

    topic = st["CandidateAlertsTopic"]
    require(topic == f"arn:aws:sns:{REGION}:{ACCOUNT}:stocklens-st-candidate-alerts",
            "ST_ALERT_TOPIC_MISMATCH")
    subscriptions = sns.list_subscriptions_by_topic(TopicArn=topic).get("Subscriptions", [])
    require(any(x.get("Protocol") == "email" and
                x.get("SubscriptionArn") not in (None, "PendingConfirmation") for x in subscriptions),
            "ST_SNS_NOT_CONFIRMED")
    isolated_names = {
        "MissingOrLateScheduledSignalsAlarm", "MissedSessionsAlarm",
        "BookHaltedAlarm", "SchedulerStateMismatchAlarm",
        "InvalidContinuityRecordAlarm", "WatchdogConfigurationErrorAlarm",
        "WatchdogFailClosedAlarm", "WatchdogHeartbeatDeadmanAlarm",
    }
    alarms = []
    for logical in ALARM_IDS:
        item = cf.describe_stack_resource(StackName=ST, LogicalResourceId=logical)
        physical_name = item["StackResourceDetail"]["PhysicalResourceId"]
        data = cw.describe_alarms(AlarmNames=[physical_name]).get("MetricAlarms", [])
        require(len(data) == 1 and data[0].get("AlarmName") == physical_name,
                "ST_ALARM_NOT_FOUND:" + logical)
        alarm = data[0]
        require(alarm.get("ActionsEnabled") is True and
                topic in alarm.get("AlarmActions", []),
                "ST_ALARM_NOT_CONNECTED_TO_EMAIL:" + logical)
        if logical in isolated_names:
            require(alarm.get("Namespace") == "StockLens/IsolatedST" and
                    not alarm.get("Dimensions"),
                    "ST_WATCHDOG_ALARM_STILL_SHARED_OR_MISCONFIGURED:" + logical)
        alarms.append({"name": logical, "state": alarm.get("StateValue")})

    severe = [x["name"] for x in alarms if x["state"] == "ALARM"]
    uncertain = [x["name"] for x in alarms if x["state"] not in ("OK", "ALARM")]
    signal = validate_signal(s3, session, now)
    if signal:
        status = "ST_SIGNAL_ACCEPTED" if signal["signal_saved_at_utc"] <= due.isoformat() else "ST_SIGNAL_LATE"
        if severe:
            status = "ST_SIGNAL_ACCEPTED_WITH_ALARM"
    elif now < due:
        status = "ST_SIGNAL_AWAITING_SCHEDULE"
    else:
        status = "ST_SIGNAL_MISSING_AFTER_DEADLINE"
    return {
        "kind": "STOCKLENS_READ_ONLY_SIGNAL_ACCEPTANCE_V1",
        "account": ACCOUNT, "checked_utc": now.isoformat(),
        "session": session, "expected_deadline_utc": due.isoformat(),
        "activation_saved_utc": marker["saved_at"].isoformat(),
        "state": status, "signal": signal,
        "watchdog_schedule": "ENABLED_HOURLY",
        "alarm_count": len(alarms), "alarms_active": severe,
        "alarms_uncertain": uncertain,
        "prod_schedules": "ALL_DISABLED",
        "st_paper_schedule": "DISABLED",
        "broker_orders": False, "aws_mutations": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--session", default="2026-10-29")
    p.add_argument("--output")
    args = p.parse_args()
    import boto3
    session = boto3.session.Session(region_name=REGION)
    services = {x: session.client(x) for x in (
        "sts", "cloudformation", "events", "s3", "sns", "cloudwatch", "lambda")}
    try:
        report = check(services, args.session)
        if report["alarms_active"] or report["state"] not in (
                "ST_SIGNAL_AWAITING_SCHEDULE", "ST_SIGNAL_ACCEPTED"):
            exit_code = 2
        else:
            exit_code = 0
    except Exception as exc:
        report = {
            "kind": "STOCKLENS_READ_ONLY_SIGNAL_ACCEPTANCE_V1",
            "state": "ST_SIGNAL_ACCEPTANCE_BLOCKED",
            "reason": str(exc)[:320], "aws_mutations": False,
            "broker_orders": False,
        }
        exit_code = 2
    rendered = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    print(rendered)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(rendered + "\n")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())

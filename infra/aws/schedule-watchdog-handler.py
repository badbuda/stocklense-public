"""Four-times-daily independent AWS schedule watchdog; read-only probe.

Archive functions do not trigger this monitor. No DynamoDB write, broker calls,
execution-mode changes, or inferred fills are permitted.
"""
from datetime import datetime, timezone
import json
import os
import boto3


def inspect(now, mapping, events, lambdas, metrics):
    if now.tzinfo is None:
        raise ValueError("WATCHDOG_CLOCK_MUST_BE_AWARE")
    now = now.astimezone(timezone.utc)
    if len(mapping) != 2 or len({x[0] for x in mapping}) != 2:
        raise ValueError("TWO_DISTINCT_SCHEDULED_RULES_REQUIRED")
    failures = []
    checked = []
    for rule, function in mapping:
        try:
            metadata = events.describe_rule(Name=rule)
            targets = events.list_targets_by_rule(Rule=rule).get("Targets", [])
            config = lambdas.get_function_configuration(FunctionName=function)
            state = config.get("State")
            expected_arn = config.get("FunctionArn")
            if metadata.get("State") != "ENABLED":
                failures.append("RULE_NOT_ENABLED:" + rule)
            if not expected_arn or not any(t.get("Arn") == expected_arn for t in targets):
                failures.append("EXPECTED_LAMBDA_NOT_TARGETED:" + rule)
            if state != "Active":
                failures.append("ARCHIVE_LAMBDA_NOT_ACTIVE:" + function)
            checked.append({"rule": rule, "rule_state": metadata.get("State"),
                            "target_found": bool(expected_arn and any(
                                t.get("Arn") == expected_arn for t in targets)),
                            "function": function, "lambda_state": state})
        except Exception as error:
            failures.append("READ_ONLY_PREFLIGHT_FAILED:" + rule + ":" + type(error).__name__)
    # Both upstream EventBridge rules run Tue-Sat, including NYSE holidays.
    # Their *invocation* is expected on holidays even if archiving is skipped.
    # This checks invocation, not the existence of a valid trading-session row.
    invocation_due = now.weekday() in (1, 2, 3, 4, 5) and 12 <= now.hour < 15
    if invocation_due:
        start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        end = now.replace(hour=12, minute=0, second=0, microsecond=0)
        for _, function in mapping:
            try:
                data = metrics.get_metric_statistics(
                    Namespace="AWS/Lambda", MetricName="Invocations",
                    Dimensions=[{"Name": "FunctionName", "Value": function}],
                    StartTime=start, EndTime=end, Period=300, Statistics=["Sum"])
                count = sum(float(p["Sum"]) for p in data.get("Datapoints", []))
                if count < 1:
                    failures.append("EXPECTED_INVOCATION_MISSING:" + function)
            except Exception as error:
                failures.append("INVOCATION_METRIC_UNAVAILABLE:" + function + ":" + type(error).__name__)
    return {"checked_utc": now.isoformat(), "archive_rules": checked,
            "invocation_check_due": invocation_due,
            "failures": failures, "status": "FAIL_CLOSED" if failures else "PASS",
            "broker_execution_authorized": False}


def handler(event, context):
    mapping = [(os.environ["SHADOW_RULE"], os.environ["SHADOW_FUNCTION"]),
               (os.environ["PAPER_RULE"], os.environ["PAPER_FUNCTION"])]
    report = inspect(datetime.now(timezone.utc), mapping,
                     boto3.client("events"), boto3.client("lambda"),
                     boto3.client("cloudwatch"))
    print(json.dumps(report, sort_keys=True))
    if report["failures"]:
        raise RuntimeError("STOCKLENS_WATCHDOG_FAIL:" + ",".join(report["failures"]))
    return report

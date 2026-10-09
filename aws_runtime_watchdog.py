"""Read-only AWS deployed runtime watchdog; NEVER broker execution or alert delivery proof.

Checks CloudFormation physical IDs, enabled EventBridge rules and correct Lambda
targets, healthy Lambda configuration, CloudWatch Errors alarms wired to SNS,
and a confirmed email subscription. All AWS calls are read-only.
Run only AFTER the updated IAM policy has been deployed to the existing stack.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from collections.abc import Callable

EXPECTED = (
    ("NightlyRule", "ShadowLambda", "ShadowArchive", "cron(10 9 ? * TUE-SAT *)"),
    ("PaperEvidenceSchedule", "PaperEvidenceLambda", "PaperEvidence",
     "cron(20 9 ? * TUE-SAT *)"),
)
ALARMS = ("ErrorAlarm", "PaperEvidenceAlarm")


class WatchdogError(RuntimeError):
    """Missing or inconsistent deployed monitoring configuration."""


def _aws(args: list[str]) -> dict:
    result = subprocess.run(
        ["aws", *args, "--output", "json"],
        capture_output=True, text=True, check=True, timeout=25,
    )
    obj = json.loads(result.stdout)
    if not isinstance(obj, dict):
        raise WatchdogError("AWS_RESPONSE_NOT_OBJECT")
    return obj


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise WatchdogError(message)


def inspect(stack: str, run: Callable[[list[str]], dict] = _aws) -> dict:
    if not stack or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_" for c in stack):
        raise ValueError("INVALID_STACK_NAME")

    def physical(logical: str) -> str:
        payload = run(["cloudformation", "describe-stack-resource",
                       "--stack-name", stack, "--logical-resource-id", logical])
        detail = payload.get("StackResourceDetail", {})
        ident = detail.get("PhysicalResourceId")
        _require(isinstance(ident, str) and bool(ident),
                 "MISSING_DEPLOYED_RESOURCE:" + logical)
        _require(detail.get("ResourceStatus") in ("CREATE_COMPLETE", "UPDATE_COMPLETE"),
                 "DEPLOYED_RESOURCE_NOT_COMPLETE:" + logical)
        return ident

    checked = []
    for logical_rule, logical_lambda, target_id, cron in EXPECTED:
        rule_name = physical(logical_rule)
        function = physical(logical_lambda)
        rule = run(["events", "describe-rule", "--name", rule_name])
        _require(rule.get("Name") == rule_name, "RULE_IDENTITY_MISMATCH:" + logical_rule)
        _require(rule.get("State") == "ENABLED", "EVENTBRIDGE_RULE_DISABLED:" + logical_rule)
        _require(rule.get("ScheduleExpression") == cron,
                 "EVENTBRIDGE_SCHEDULE_DRIFT:" + logical_rule)
        targets = run(["events", "list-targets-by-rule", "--rule", rule_name]).get("Targets")
        _require(isinstance(targets, list), "EVENTBRIDGE_TARGETS_MISSING:" + logical_rule)
        cfg = run(["lambda", "get-function-configuration", "--function-name", function])
        _require(cfg.get("FunctionName") == function,
                 "LAMBDA_IDENTITY_MISMATCH:" + logical_lambda)
        _require(cfg.get("State") == "Active",
                 "LAMBDA_NOT_ACTIVE:" + logical_lambda)
        _require(cfg.get("LastUpdateStatus") == "Successful",
                 "LAMBDA_UPDATE_NOT_SUCCESSFUL:" + logical_lambda)
        arn = cfg.get("FunctionArn")
        _require(isinstance(arn, str) and arn.startswith("arn:"),
                 "LAMBDA_ARN_MISSING:" + logical_lambda)
        _require(any(t.get("Id") == target_id and t.get("Arn") == arn for t in targets
                     if isinstance(t, dict)),
                 "EVENTBRIDGE_TARGET_NOT_EXPECTED_LAMBDA:" + logical_rule)
        checked.append({"rule": logical_rule, "enabled": True,
                        "schedule_matches": True, "target_matches": True,
                        "lambda": logical_lambda, "lambda_active": True})

    # CloudFormation condition EmailAlertsConfigured can omit PaperAlertTopic.
    # An absent topic is NOT a successful monitoring deployment.
    topic = physical("PaperAlertTopic")
    _require(topic.startswith("arn:") and ":sns:" in topic,
             "INVALID_SNS_TOPIC_ARN")
    alarm_results = []
    for logical in ALARMS:
        alarm_name = physical(logical)
        response = run(["cloudwatch", "describe-alarms", "--alarm-names", alarm_name])
        alarms = response.get("MetricAlarms")
        _require(isinstance(alarms, list) and len(alarms) == 1
                 and alarms[0].get("AlarmName") == alarm_name,
                 "CLOUDWATCH_ALARM_NOT_FOUND:" + logical)
        alarm = alarms[0]
        _require(alarm.get("ActionsEnabled") is True,
                 "CLOUDWATCH_ALARM_ACTIONS_DISABLED:" + logical)
        _require(topic in alarm.get("AlarmActions", []),
                 "CLOUDWATCH_ALARM_NOT_WIRED_TO_SNS:" + logical)
        _require(alarm.get("MetricName") == "Errors"
                 and alarm.get("Namespace") == "AWS/Lambda",
                 "CLOUDWATCH_ALARM_METRIC_DRIFT:" + logical)
        alarm_results.append({"alarm": logical, "actions_enabled": True,
                              "sns_topic_attached": True})

    subscriptions = run(["sns", "list-subscriptions-by-topic",
                         "--topic-arn", topic]).get("Subscriptions")
    _require(isinstance(subscriptions, list), "SNS_SUBSCRIPTIONS_UNAVAILABLE")
    _require(any(isinstance(sub, dict) and sub.get("Protocol") == "email"
                 and isinstance(sub.get("SubscriptionArn"), str)
                 and sub["SubscriptionArn"].startswith("arn:")
                 and sub.get("TopicArn") == topic for sub in subscriptions),
             "SNS_EMAIL_SUBSCRIPTION_UNCONFIRMED")
    return {
        "schema_version": 1,
        "status": "DEPLOYED_CONFIG_VERIFIED_NOT_DELIVERY_PROOF",
        "stack": stack,
        "eventbridge": checked,
        "alarms": alarm_results,
        "sns_confirmed_email_subscription": True,
        "cloudwatch_invocation_metrics_verified": False,
        "actual_alert_received_verified": False,
        "missed_invocation_notification_verified": False,
        "aws_stack_deployment_proven_by_this_source_file": False,
        "broker_fills_observed": False,
        "live_trading_authorized": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stack", default="stocklens-paper")
    args = parser.parse_args()
    try:
        result = inspect(args.stack)
    except (WatchdogError, ValueError, subprocess.CalledProcessError,
            subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        # Do not print subprocess stderr, AWS account IDs, subscription endpoints
        # or raw AWS responses to public CI logs.
        label = str(exc) if isinstance(exc, (WatchdogError, ValueError)) else type(exc).__name__
        print(json.dumps({"status": "AWS_RUNTIME_WATCHDOG_FAIL_CLOSED",
                          "error": label, "live_trading_authorized": False}))
        raise SystemExit(2) from None
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

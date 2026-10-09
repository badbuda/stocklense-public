"""Offline read-only monitoring checks."""
from copy import deepcopy
import pytest
from aws_runtime_watchdog import EXPECTED, WatchdogError, inspect


def example():
    resources = {
        "NightlyRule": "rule-shadow",
        "PaperEvidenceSchedule": "rule-paper",
        "ShadowLambda": "function-shadow",
        "PaperEvidenceLambda": "function-paper",
        "ErrorAlarm": "alarm-shadow",
        "PaperEvidenceAlarm": "alarm-paper",
        "PaperAlertTopic": "arn:aws:sns:region:account:topic",
    }
    replies = {}
    for logical, name in resources.items():
        replies[("cloudformation", "describe-stack-resource", logical)] = {
            "StackResourceDetail": {
                "PhysicalResourceId": name,
                "ResourceStatus": "CREATE_COMPLETE"}}
    for rule, function, target_id, cron in EXPECTED:
        name = resources[rule]
        fn = resources[function]
        arn = "arn:aws:lambda:region:account:function:" + fn
        replies[("events", "describe-rule", name)] = {
            "Name": name, "State": "ENABLED", "ScheduleExpression": cron}
        replies[("events", "list-targets-by-rule", name)] = {
            "Targets": [{"Id": target_id, "Arn": arn}]}
        replies[("lambda", "get-function-configuration", fn)] = {
            "FunctionName": fn, "FunctionArn": arn,
            "State": "Active", "LastUpdateStatus": "Successful"}
    for logical in ("ErrorAlarm", "PaperEvidenceAlarm"):
        name = resources[logical]
        replies[("cloudwatch", "describe-alarms", name)] = {
            "MetricAlarms": [{"AlarmName": name, "ActionsEnabled": True,
                              "AlarmActions": [resources["PaperAlertTopic"]],
                              "MetricName": "Errors", "Namespace": "AWS/Lambda"}]}
    replies[("sns", "list-subscriptions-by-topic", resources["PaperAlertTopic"])] = {
        "Subscriptions": [{"Protocol": "email",
                           "SubscriptionArn": "arn:aws:sns:region:account:sub",
                           "TopicArn": resources["PaperAlertTopic"],
                           "Endpoint": "masked"}]}
    return resources, replies


def run(replies, seen=None):
    def fake(args):
        if seen is not None:
            seen.append(tuple(args))
        return deepcopy(replies[(args[0], args[1], args[-1])])
    return inspect("stocklens-paper", fake)


def test_healthy_configuration_does_not_prove_alert_delivery():
    _, replies = example()
    seen = []
    result = run(replies, seen)
    assert result["status"] == "DEPLOYED_CONFIG_VERIFIED_NOT_DELIVERY_PROOF"
    assert len(result["eventbridge"]) == 2
    assert len(result["alarms"]) == 2
    assert result["actual_alert_received_verified"] is False
    assert result["live_trading_authorized"] is False
    assert len(seen) == 16
    assert "masked" not in str(result)


def test_invalid_stack_name():
    with pytest.raises(ValueError, match="INVALID_STACK_NAME"):
        inspect("invalid stack name", lambda _: {})


def test_missing_stack_resource():
    with pytest.raises(KeyError):
        inspect("stocklens-paper", lambda _: {})

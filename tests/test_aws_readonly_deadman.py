"""No AWS calls: read-only configuration watchdog unit tests."""
from aws_readonly_deadman import inspect


def healthy(*args):
    if args[:2] == ("events", "describe-rule"):
        return {"State": "ENABLED"}
    if args[:2] == ("events", "list-targets-by-rule"):
        return {"Targets": [{"Id": "archive"}]}
    if args[:2] == ("lambda", "get-function-configuration"):
        return {"State": "Active"}
    raise AssertionError(args)


def test_healthy_is_not_claim_of_delivery():
    result = inspect(["nightly"], ["shadow"], client=healthy)
    assert result["status"] == "PASS_READ_ONLY_CONFIGURATION"
    assert result["sns_delivery_proven"] is False
    assert result["invocation_delivery_proven"] is False


def test_disabled_rule_fails_closed():
    def client(*args):
        if args[:2] == ("events", "describe-rule"):
            return {"State": "DISABLED"}
        return healthy(*args)
    assert inspect(["nightly"], ["shadow"], client=client)["status"] == "FAIL_CLOSED"


def test_missing_target_fails_closed():
    def client(*args):
        if args[:2] == ("events", "list-targets-by-rule"):
            return {"Targets": []}
        return healthy(*args)
    assert inspect(["nightly"], ["shadow"], client=client)["errors"]


def test_denied_aws_permission_fails_closed():
    def client(*args):
        raise PermissionError("denied")
    result = inspect(["nightly"], ["shadow"], client=client)
    assert len(result["errors"]) == 2


def test_inactive_lambda_fails_closed():
    def client(*args):
        if args[:2] == ("lambda", "get-function-configuration"):
            return {"State": "Inactive"}
        return healthy(*args)
    assert inspect(["nightly"], ["shadow"], client=client)["status"] == "FAIL_CLOSED"

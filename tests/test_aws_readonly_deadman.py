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

def test_expected_session_detects_missing_invocation():
    from datetime import datetime, timezone
    class Cal:
        def is_session(self, day): return True
    def fake(*args):
        if args[:2] == ("cloudwatch", "get-metric-statistics"): return {"Datapoints": []}
        return healthy(*args)
    r = inspect(["nightly"], ["shadow"], now=datetime(2026, 10, 10, 9, 45, tzinfo=timezone.utc),
                client=fake, check_invocations=True, calendar=Cal())
    assert "MISSED_INVOCATION:shadow" in r["errors"]

def test_expected_session_observed_invocation_does_not_prove_alert():
    from datetime import datetime, timezone
    class Cal:
        def is_session(self, day): return True
    def fake(*args):
        if args[:2] == ("cloudwatch", "get-metric-statistics"): return {"Datapoints": [{"Sum": 1.0}]}
        return healthy(*args)
    r = inspect(["nightly"], ["shadow"], now=datetime(2026, 10, 10, 9, 45, tzinfo=timezone.utc),
                client=fake, check_invocations=True, calendar=Cal())
    assert r["status"] == "PASS_READ_ONLY_CONFIGURATION"
    assert r["invocation_window_checked"] and not r["sns_delivery_proven"]

def test_holiday_skips_metric_requirement_but_checks_configuration():
    from datetime import datetime, timezone
    class Cal:
        def is_session(self, day): return False
    r = inspect(["nightly"], ["shadow"], now=datetime(2026, 10, 10, 9, 45, tzinfo=timezone.utc),
                client=healthy, check_invocations=True, calendar=Cal())
    assert r["expected_xnys_session"] is False
    assert r["status"] == "PASS_READ_ONLY_CONFIGURATION"

def test_metrics_before_settle_window_fail_closed():
    from datetime import datetime, timezone
    class Cal:
        def is_session(self, day): return True
    r = inspect(["nightly"], ["shadow"], now=datetime(2026, 10, 10, 9, 30, tzinfo=timezone.utc),
                client=healthy, check_invocations=True, calendar=Cal())
    assert "AUDIT_BEFORE_INVOCATION_METRICS_SETTLED" in r["errors"]

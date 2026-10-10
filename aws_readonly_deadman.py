"""Read-only deployed EventBridge/Lambda health evidence. Never sends orders or mutates AWS."""
import argparse
import json
import subprocess
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo


def aws(*args):
    result = subprocess.run(["aws", *args, "--output", "json"], capture_output=True,
                            text=True, check=True, timeout=25)
    return json.loads(result.stdout)


def inspect(rule_names, function_names, now=None, client=aws, *, check_invocations=False, calendar=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("aware UTC clock required")
    evidence = {"checked_at_utc": now.isoformat(), "rules": [], "lambdas": [],
                "invocation_window_checked": False, "expected_xnys_session": None,
                "sns_delivery_proven": False, "broker_trading_authorized": False}
    errors = []
    for name in rule_names:
        try:
            rule = client("events", "describe-rule", "--name", name)
            targets = client("events", "list-targets-by-rule", "--rule", name).get("Targets", [])
            state = rule.get("State")
            evidence["rules"].append({"name": name, "state": state, "targets": len(targets)})
            if state != "ENABLED" or not targets:
                errors.append("DISABLED_OR_TARGETLESS_RULE:" + name)
        except Exception as exc:
            errors.append("RULE_INSPECTION_FAILED:" + name + ":" + type(exc).__name__)
    for name in function_names:
        try:
            function = client("lambda", "get-function-configuration", "--function-name", name)
            state = function.get("State")
            evidence["lambdas"].append({"name": name, "state": state})
            if state != "Active":
                errors.append("INACTIVE_LAMBDA:" + name)
        except Exception as exc:
            errors.append("LAMBDA_INSPECTION_FAILED:" + name + ":" + type(exc).__name__)
    if check_invocations:
        # Check a completed XNYS session only; metrics may lag the cron.
        try:
            import exchange_calendars as xcals
            prior = (now.astimezone(ZoneInfo("America/New_York")).date() - timedelta(days=1)).isoformat()
            cal = calendar if calendar is not None else xcals.get_calendar("XNYS")
            expected = bool(cal.is_session(prior))
            evidence["expected_xnys_session"] = expected
            evidence["session_checked"] = prior
            utc_now = now.astimezone(timezone.utc)
            start = utc_now.replace(hour=9, minute=0, second=0, microsecond=0)
            if expected and utc_now < start + timedelta(minutes=40):
                errors.append("AUDIT_BEFORE_INVOCATION_METRICS_SETTLED")
            elif expected:
                evidence["invocation_window_checked"] = True
                for name in function_names:
                    try:
                        r = client("cloudwatch", "get-metric-statistics", "--namespace", "AWS/Lambda",
                                   "--metric-name", "Invocations", "--dimensions", "Name=FunctionName,Value=" + name,
                                   "--start-time", start.isoformat(), "--end-time", utc_now.isoformat(),
                                   "--period", "60", "--statistics", "Sum")
                        if sum(float(x["Sum"]) for x in r.get("Datapoints", [])) < 1:
                            errors.append("MISSED_INVOCATION:" + name)
                    except Exception as exc:
                        errors.append("INVOCATION_CHECK_FAILED:" + name + ":" + type(exc).__name__)
        except Exception as exc:
            errors.append("XNYS_CALENDAR_CHECK_FAILED:" + type(exc).__name__)
    evidence["errors"] = errors
    evidence["status"] = "PASS_READ_ONLY_CONFIGURATION" if not errors else "FAIL_CLOSED"
    evidence["invocation_delivery_proven"] = False
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rule", action="append", required=True)
    parser.add_argument("--function", action="append", required=True)
    parser.add_argument("--check-invocations", action="store_true")
    args = parser.parse_args()
    result = inspect(args.rule, args.function, check_invocations=args.check_invocations)
    print(json.dumps(result, sort_keys=True))
    if result["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

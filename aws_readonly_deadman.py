"""Read-only deployed EventBridge/Lambda health evidence. Never sends orders or mutates AWS."""
import argparse
import json
import subprocess
from datetime import datetime, timezone, timedelta


def aws(*args):
    result = subprocess.run(["aws", *args, "--output", "json"], capture_output=True,
                            text=True, check=True, timeout=25)
    return json.loads(result.stdout)


def inspect(rule_names, function_names, now=None, client=aws):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("aware UTC clock required")
    evidence = {"checked_at_utc": now.isoformat(), "rules": [], "lambdas": [],
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
    evidence["errors"] = errors
    evidence["status"] = "PASS_READ_ONLY_CONFIGURATION" if not errors else "FAIL_CLOSED"
    evidence["invocation_delivery_proven"] = False
    return evidence


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--rule", action="append", required=True)
    parser.add_argument("--function", action="append", required=True)
    args = parser.parse_args()
    result = inspect(args.rule, args.function)
    print(json.dumps(result, sort_keys=True))
    if result["errors"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

"""Fail-closed reviewer of an inert CloudFormation legacy-retirement change set.

This verifier authorizes ONLY exact in-place State changes to three EventBridge
rules and notification/TreatMissingData changes to four legacy CloudWatch alarms.
CloudFormation retain-policy on the DynamoDB historical table must not change.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RULES = {"NightlyRule", "PaperEvidenceSchedule", "WatchdogSchedule"}
ALARMS = {"ErrorAlarm", "PaperEvidenceAlarm", "WatchdogErrorAlarm", "WatchdogHeartbeatAlarm"}
ALLOWED = {
    **{name: {"State"} for name in RULES},
    **{name: {"AlarmActions"} for name in ALARMS},
}
ALLOWED["WatchdogHeartbeatAlarm"] = {"AlarmActions", "TreatMissingData"}


def validate_changeset(payload: dict) -> dict:
    if payload.get("Status") != "CREATE_COMPLETE":
        raise ValueError("CHANGESET_NOT_READY")
    if payload.get("StackName") != "stocklens-paper":
        raise ValueError("UNEXPECTED_LEGACY_STACK")
    parameters = {p["ParameterKey"]: p.get("ParameterValue") for p in payload.get("Parameters", [])}
    if parameters.get("LegacyRetirementMode") != "RETIRED":
        raise ValueError("RETIREMENT_PARAMETER_NOT_RETIRED")
    changes = payload.get("Changes", [])
    seen = set()
    if len(changes) != len(ALLOWED):
        raise ValueError("EXPECTED_EXACTLY_SEVEN_NON_DESTRUCTIVE_RESOURCE_UPDATES")
    for change in changes:
        resource = change.get("ResourceChange", {})
        logical = resource.get("LogicalResourceId")
        if logical not in ALLOWED or logical in seen:
            raise ValueError("UNEXPECTED_OR_DUPLICATE_CHANGE:" + str(logical))
        seen.add(logical)
        if resource.get("Action") != "Modify" or resource.get("Replacement") not in ("False", False):
            raise ValueError("DESTRUCTIVE_CHANGE_REFUSED:" + logical)
        expected_type = ("AWS::Events::Rule" if logical in RULES
                         else "AWS::CloudWatch::Alarm")
        if resource.get("ResourceType") != expected_type:
            raise ValueError("UNEXPECTED_RESOURCE_TYPE:" + logical)
        if set(resource.get("Scope", [])) != {"Properties"}:
            raise ValueError("UNEXPECTED_CHANGE_SCOPE:" + logical)
        details = resource.get("Details")
        if not details:
            raise ValueError("UNKNOWN_CHANGE_DETAILS:" + logical)
        seen_props = set()
        for detail in details:
            target = detail.get("Target", {})
            if target.get("Attribute") != "Properties":
                raise ValueError("NONPROPERTY_CHANGE:" + logical)
            prop = target.get("Name")
            if prop not in ALLOWED[logical]:
                raise ValueError("UNEXPECTED_PROPERTY_MODIFICATION:" + logical + ":" + str(prop))
            if target.get("RequiresRecreation") != "Never":
                raise ValueError("RECREATION_REQUIRED:" + logical)
            seen_props.add(prop)
        if "State" in ALLOWED[logical] and "State" not in seen_props:
            raise ValueError("RULE_NOT_BEING_DISABLED:" + logical)
        if "AlarmActions" in ALLOWED[logical] and "AlarmActions" not in seen_props:
            raise ValueError("ALARM_NOTIFICATIONS_NOT_BEING_RETIRED:" + logical)
    return {
        "status": "REVIEWED_CHANGESET_NONDESTRUCTIVE_EXACTLY_7",
        "disabled_eventbridge_rules": sorted(RULES),
        "retired_cloudwatch_alarm_notifications": sorted(ALARMS),
        "dynamodb_table_mutated": False,
        "iam_mutated": False,
        "new_staging_mutated": False,
        "validated_only_no_cloudformation_execution": True,
    }


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: verify_legacy_retirement_changeset.py downloaded_change_set.json")
    try:
        payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
        print(json.dumps(validate_changeset(payload), indent=2, sort_keys=True))
    except (ValueError, KeyError, TypeError) as exc:
        print("REFUSE_LEGACY_CHANGESET:" + str(exc), file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

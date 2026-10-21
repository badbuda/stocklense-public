"""No-cloud retirement release contract: preserve old evidence and new Signal."""
from __future__ import annotations

import copy
from pathlib import Path
import subprocess

import pytest
import yaml

from infra.aws.verify_legacy_retirement_changeset import (
    validate_changeset, ALLOWED, RULES, ALARMS,
)

TEMPLATE = Path("infra/aws/paper-signal-journal.yaml")
SCRIPT = Path("infra/aws/retire_legacy_stocklens.sh")


class Loader(yaml.SafeLoader):
    pass


Loader.add_multi_constructor("!", lambda loader, tag, node:
    tag + ":" + str(node.value) if isinstance(node, yaml.ScalarNode) else
    (tag + ":" + str(loader.construct_sequence(node))
     if isinstance(node, yaml.SequenceNode) else
     tag + ":" + str(loader.construct_mapping(node))))


def resources():
    return yaml.load(TEMPLATE.read_text(), Loader=Loader)


def test_default_decommissions_three_and_keeps_old_table():
    raw = TEMPLATE.read_text()
    doc = resources()
    assert doc["Parameters"]["LegacyRetirementMode"]["Default"] == "RETIRED"
    assert doc["Parameters"]["LegacyRetirementMode"]["AllowedValues"] == [
        "RUNNING", "RETIRED"]
    all_res = doc["Resources"]
    assert all_res["Signals"]["DeletionPolicy"] == "Retain"
    assert all_res["Signals"]["Type"] == "AWS::DynamoDB::Table"
    assert all_res["GitHubAuditRole"]["Type"] == "AWS::IAM::Role"
    assert all_res["GitHubOIDC"]["Type"] == "AWS::IAM::OIDCProvider"
    assert doc["Outputs"]["TableName"]
    assert len([x for x in all_res.values()
                if x["Type"] == "AWS::Events::Rule"]) == 3
    for n in RULES:
        assert all_res[n]["Properties"]["State"].startswith("If:")
        assert "LegacyArchiveRunning" in all_res[n]["Properties"]["State"]
    for n in ALARMS:
        alarm = all_res[n]["Properties"]
        assert alarm["AlarmActions"].startswith("If:")
        assert "LegacyNotify" in alarm["AlarmActions"]
        assert alarm["TreatMissingData"] in ("notBreaching",) or n == "WatchdogHeartbeatAlarm"
    assert "LegacyArchiveRunning, breaching, notBreaching" in raw
    # Never send new production/standalone Staging into this stack.
    assert "stocklens-independent-staging" not in raw


def example_changeset():
    changes = []
    for name in sorted(ALLOWED):
        changed_properties = ({"State"} if name in RULES else
                              ({"AlarmActions", "TreatMissingData"} if name == "WatchdogHeartbeatAlarm"
                               else {"AlarmActions"}))
        details = [
            {"Target":{"Attribute":"Properties","Name":prop,
                       "RequiresRecreation":"Never"}}
            for prop in sorted(changed_properties)]
        changes.append({"ResourceChange":{
            "Action":"Modify","LogicalResourceId":name,
            "ResourceType":("AWS::Events::Rule" if name in RULES else "AWS::CloudWatch::Alarm"),
            "Replacement":"False","Scope":["Properties"],"Details":details}})
    return {"Status":"CREATE_COMPLETE","StackName":"stocklens-paper",
            "Parameters":[{"ParameterKey":"LegacyRetirementMode","ParameterValue":"RETIRED"}],
            "Changes":changes}


def test_exact_7_resource_updates_approved():
    report = validate_changeset(example_changeset())
    assert report["status"] == "REVIEWED_CHANGESET_NONDESTRUCTIVE_EXACTLY_7"
    assert not report["dynamodb_table_mutated"]
    assert not report["iam_mutated"]
    assert not report["new_staging_mutated"]


@pytest.mark.parametrize("evil", [
    "DeleteTable","UpdateIAM","ReplaceRule","ExtraResource","ExtraAlarmProp",
    "NoChangedAlarm","WrongParam","WrongStack",
])
def test_forbidden_changeset_fails_closed(evil):
    p = example_changeset()
    if evil == "DeleteTable":
        p["Changes"].append({"ResourceChange":{"Action":"Remove",
                                 "LogicalResourceId":"Signals","ResourceType":"AWS::DynamoDB::Table"}})
    elif evil == "UpdateIAM":
        p["Changes"][0]["ResourceChange"]["LogicalResourceId"] = "LambdaRole"
    elif evil == "ReplaceRule":
        rule = next(c for c in p["Changes"]
                    if c["ResourceChange"]["LogicalResourceId"] in RULES)
        rule["ResourceChange"]["Replacement"] = "True"
    elif evil == "ExtraResource":
        p["Changes"].append(copy.deepcopy(p["Changes"][0]))
    elif evil == "ExtraAlarmProp":
        alarm = next(c for c in p["Changes"]
                     if c["ResourceChange"]["LogicalResourceId"] in ALARMS)
        alarm["ResourceChange"]["Details"].append({"Target":{
            "Attribute":"Properties","Name":"MetricName","RequiresRecreation":"Never"}})
    elif evil == "NoChangedAlarm":
        alarm = next(c for c in p["Changes"]
                     if c["ResourceChange"]["LogicalResourceId"] == "PaperEvidenceAlarm")
        alarm["ResourceChange"]["Details"] = [{
            "Target":{"Attribute":"Properties","Name":"TreatMissingData",
                      "RequiresRecreation":"Never"}}]
    elif evil == "WrongParam":
        p["Parameters"][0]["ParameterValue"] = "RUNNING"
    elif evil == "WrongStack":
        p["StackName"] = "stocklens-independent-staging"
    with pytest.raises(ValueError):
        validate_changeset(p)


def test_retirement_shell_requires_pinned_review_and_operator_opt_in():
    subprocess.run(["bash", "-n", str(SCRIPT)], check=True)
    source = SCRIPT.read_text()
    for key in (
        "EXPECTED_LEGACY_RETIRE_COMMIT",
        "REQUIRE_GREEN_REVIEWED_LEGACY_RETIRE_SHA",
        "REFUSE_NONPINNED_GIT_HEAD",
        "REFUSE_DIRTY_GIT_TREE",
        "ci_transfer_guard.py",
        "verify_legacy_retirement_changeset.py",
        "RETIRE_OLD_STOCKLENS_PAPER_SCHEDULES",
        "aws cloudformation execute-change-set",
        "aws cloudformation wait stack-update-complete",
        "LEGACY_RETIREMENT_VERIFIED",
        "LEGACY_DYNAMODB:ACTIVE",
        "STAGING_SIGNAL:ENABLED",
        "LEGACY_HEARTBEAT_NOT_RETIRED",
    ):
        assert key in source
    assert source.index("verify_legacy_retirement_changeset.py") < source.index(
        "RETIRE_OLD_STOCKLENS_PAPER_SCHEDULES")
    assert source.index("RETIRE_OLD_STOCKLENS_PAPER_SCHEDULES") < source.index(
        "aws cloudformation execute-change-set")
    for forbidden in (
        "aws events disable-rule", "aws cloudwatch disable-alarm-actions",
        "aws dynamodb delete", "aws cloudformation delete-stack",
        "aws cloudformation update-stack", "aws s3api put-object",
    ):
        assert forbidden not in source

"""Release gates: only five Lambda Code changes may be executed in ST."""
import base64
from pathlib import Path
import pytest

from infra.aws import st_paper_cfn_guarded_release as m


def state():
    return {
        "parameters": {
            "ArtifactKey":"releases/old.zip",
            "ArtifactBucket":"internal",
            "CandidateSignalScheduleState":"DISABLED",
            "ExpectedSchedulerState":"DISABLED",
            "MonitoringStartSession":"2026-10-30",
        },
        "source_artifact_key":"releases/old.zip",
        "source_artifact_bucket":"internal",
        "expected_lambda_resources":{
            "CandidateLambda":"stocklens-st-candidate",
            "CandidatePaperLambda":"stocklens-st-paper-candidate",
            "CandidateOrchestratorLambda":"stocklens-st-orchestrator",
            "CandidatePaperPreflightLambda":"stocklens-st-paper-preflight",
            "CandidateSessionWatchdogLambda":"stocklens-st-session-watchdog",
        }
    }


def planned_change():
    s=state()
    return {
        "StackName":m.ST,"ChangeSetName":m.CHANGE_NAME,
        "Status":"CREATE_COMPLETE","ExecutionStatus":"AVAILABLE",
        "Parameters":[
            {"ParameterKey":k,"ParameterValue":m.planned_key(s) if k=="ArtifactKey" else v}
            for k,v in s["parameters"].items()
        ],
        "Changes":[{"ResourceChange":{
            "LogicalResourceId":logical,
            "ResourceType":"AWS::Lambda::Function","Action":"Modify",
            "Replacement":"False",
            "Details":[{"Target":{"Attribute":"Properties","Name":"Code",
                                   "RequiresRecreation":"Never"},
                        "ChangeSource":"ParameterReference"}]
        }} for logical in s["expected_lambda_resources"]]
    }


def test_exact_five_lambda_code_changes_are_required():
    assert len(m.validate_change_set(planned_change(),state()))==5


@pytest.mark.parametrize("changed",[
    lambda p: p["Changes"].append({"ResourceChange":{
        "LogicalResourceId":"CandidatePaperOnlyRule",
        "Action":"Modify","ResourceType":"AWS::Events::Rule","Replacement":"False"}}),
    lambda p: p["Changes"][0]["ResourceChange"].update({"Replacement":"True"}),
    lambda p: p["Changes"][0]["ResourceChange"]["Details"][0]["Target"].update(
        {"Name":"Environment"}),
    lambda p: p["Changes"].pop(),
    lambda p: p["Parameters"][0].update({"ParameterValue":"attack"}),
])
def test_change_set_rejects_rule_environment_replacement_missing_lambdas_or_param(changed):
    p=planned_change()
    changed(p)
    with pytest.raises(RuntimeError):
        m.validate_change_set(p,state())


def test_candidate_filename_and_s3_key_are_content_addressed():
    assert m.planned_key(state()).startswith("releases/stocklens-st-paper-")
    assert m.planned_key(state()).endswith(".zip")
    assert ".stocklens-private-st-releases" in str(m.package_path())


def test_apply_requires_explicit_approval_before_any_aws_reads():
    with pytest.raises(RuntimeError,match="REQUIRES_EXPLICIT"):
        m.apply(None,approved=False)


def test_no_broker_or_out_of_band_lambda_updates():
    txt=Path("infra/aws/st_paper_cfn_guarded_release.py").read_text()
    for banned in (
        ".update_function_code(", ".update_function_configuration(",
        ".enable_rule(", ".disable_rule(", ".invoke(", ".set_alarm_state(",
        ".put_metric_alarm(", ".delete_object(", ".delete_stack(",
    ):
        assert banned not in txt
    assert 'c["cloudformation"].execute_change_set(' in txt
    assert 'validate_change_set(desc,state)' in txt
    assert 'approved=False' in txt


def test_review_existing_change_set_is_readonly_and_paginates(monkeypatch):
    full = planned_change()
    a = {**full, "Changes": full["Changes"][:2], "NextToken": "page-two"}
    b = {**full, "Changes": full["Changes"][2:]}
    calls = []
    class CloudFormation:
        def describe_change_set(self, **kwargs):
            calls.append(kwargs)
            return a if len(calls) == 1 else b
        def __getattr__(self, name):
            raise AssertionError("READONLY_REVIEW_MUST_NOT_MUTATE:" + name)
    monkeypatch.setattr(m, "safe_state", lambda _: state())
    out = m.review_existing_change_set({"cloudformation": CloudFormation()})
    assert out["status"] == "EXACT_FIVE_CODE_ONLY_VALIDATED_NOT_EXECUTED"
    assert out["change_count"] == 5
    assert out["aws_mutations"] is False
    assert out["change_set_executed"] is False
    assert len(calls) == 2
    assert calls[1]["NextToken"] == "page-two"
    assert len(out["validated_lambda_code_resources"]) == 5


def test_review_surfaces_unsafe_environment_without_relaxing_gate(monkeypatch):
    raw = planned_change()
    raw["Changes"][0]["ResourceChange"]["Details"].append({
        "Target": {"Attribute": "Properties", "Name": "Environment",
                   "RequiresRecreation": "Never"},
        "ChangeSource": "ParameterReference",
        "CausingEntity": "CandidateSignalScheduleState",
        "Evaluation": "Static",
        "BeforeValue": "secret-before",
        "AfterValue": "secret-after",
    })
    class CloudFormation:
        def describe_change_set(self, **kwargs):
            return raw
        def __getattr__(self, name):
            raise AssertionError("MUTATION_NOT_PERMITTED:" + name)
    monkeypatch.setattr(m, "safe_state", lambda _: state())
    out = m.review_existing_change_set({"cloudformation": CloudFormation()})
    assert out["status"] == "BLOCKED_PENDING_MANUAL_REVIEW"
    assert out["validator_block_reason"] == "CFN_CHANGE_NOT_CODE_ONLY:CandidateLambda"
    assert out["resource_changes"][0]["details"][-1]["property"] == "Environment"
    assert out["resource_changes"][0]["details"][-1]["causing_entity"] == "CandidateSignalScheduleState"
    rendered = __import__("json").dumps(out)
    assert "secret-before" not in rendered and "secret-after" not in rendered


def test_review_does_not_accept_unsafe_code_change_source(monkeypatch):
    raw = planned_change()
    raw["Changes"][0]["ResourceChange"]["Details"][0]["ChangeSource"] = "ResourceReference"
    class CloudFormation:
        def describe_change_set(self, **kwargs):
            return raw
    monkeypatch.setattr(m, "safe_state", lambda _: state())
    out = m.review_existing_change_set({"cloudformation": CloudFormation()})
    assert out["status"] == "BLOCKED_PENDING_MANUAL_REVIEW"
    assert out["resource_changes"][0]["details"][0]["source"] == "ResourceReference"
    assert out["change_set_executed"] is False


def test_review_redacts_unexpected_causing_entities(monkeypatch):
    raw = planned_change()
    raw["Changes"][0]["ResourceChange"]["Details"][0].update(
        {"CausingEntity": "arn:aws:secretsmanager:prod:private:secret"}
    )
    class CloudFormation:
        def describe_change_set(self, **kwargs):
            return raw
    monkeypatch.setattr(m, "safe_state", lambda _: state())
    out = m.review_existing_change_set({"cloudformation": CloudFormation()})
    assert out["resource_changes"][0]["details"][0]["causing_entity"] == "REDACTED"

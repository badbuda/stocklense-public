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

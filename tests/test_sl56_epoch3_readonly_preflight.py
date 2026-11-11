"""ST epoch3 acceptance preflight cannot mutate or silently accept old gap."""
import hashlib
import io
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from infra.aws import sl56_epoch3_readonly_preflight as m
from stocklens import paper_epoch3 as epoch


class NotFound(Exception):
    response={"Error":{"Code":"404"}}


def fake_services(*, prod_enabled=False, changed_old=False,
                  occupied_gap=False, signal_sha=None):
    data={}
    for key, sha in epoch.HISTORIC_SHA256.items():
        # Simulated digest is overridden by direct sha in test to avoid
        # inventing a fake preimage for immutable pinned AWS objects.
        data[key]=b"historic"
    if occupied_gap:
        data["paper/sessions/2026-11-05.json"]=b'{"invented":true}'
    outs=lambda kind: {
        "CandidateDataBucket":(m.BUCKET if kind=="stocklens-st" else m.PROD_BUCKET),
        "CandidateFunctionName":"stocklens-st-candidate",
        "CandidatePaperOnlyRuleName":kind+"-paper",
        "CandidateSignalOnlyRuleName":kind+"-signal",
        "CandidateOrchestratorRuleName":kind+"-orchestrator",
    }
    versions=lambda kind: {"Stacks":[{"StackStatus":"UPDATE_COMPLETE",
        "Outputs":[{"OutputKey":k,"OutputValue":v} for k,v in outs(kind).items()]}]}
    class S3:
        def get_bucket_versioning(self,*,Bucket):
            assert Bucket==m.BUCKET
            return {"Status":"Enabled"}
        def head_object(self,*,Bucket,Key):
            assert Bucket==m.BUCKET
            if Key not in data:raise NotFound
            return {"VersionId":"test-v1","ContentLength":len(data[Key]),
                    "LastModified":datetime(2026,11,12,8,30,tzinfo=timezone.utc)}
        def get_object(self,*,Bucket,Key,VersionId):
            assert VersionId=="test-v1"
            return {"VersionId":"test-v1","Body":io.BytesIO(data[Key])}
    ev=SimpleNamespace(describe_rule=lambda Name:{
        "State":"ENABLED" if Name=="stocklens-st-paper" or (
            prod_enabled and Name=="stocklens-prod-paper") else "DISABLED"})
    services={
        "sts":SimpleNamespace(get_caller_identity=lambda:{"Account":m.ACCOUNT}),
        "cloudformation":SimpleNamespace(describe_stacks=lambda StackName:versions(StackName)),
        "events":ev,
        "lambda":SimpleNamespace(get_function_configuration=lambda FunctionName:{
            "State":"Active","LastUpdateStatus":"Successful",
            "CodeSha256":signal_sha or m.SIGNAL_CODE_SHA_B64}),
        "s3":S3(),
    }
    return services, data


def test_exact_source_scope_no_mutations_or_lambda_invoke():
    from pathlib import Path
    source=Path("infra/aws/sl56_epoch3_readonly_preflight.py").read_text()
    for forbidden in ("put_object(", "delete_object(", ".invoke(", "update_function",
                      "enable_rule(", "disable_rule(", "set_alarm_state(",
                      "place_order(", "execute_change_set("):
        assert forbidden not in source
    assert "deployment_authorized" in source
    assert "old_book_and_original_alarms_preserved" in source


def test_prehistoric_pin_mismatch_fails_closed(monkeypatch):
    services,_=fake_services()
    with pytest.raises(RuntimeError,match="OLD_BOOK_PIN_CHANGED"):
        m.preflight(services)


def test_pins_verified_and_gap_missing_yields_planning_only(monkeypatch):
    services,_=fake_services()
    original=m.current_version
    def pinned(client,key,*,required):
        result=original(client,key,required=required)
        if result is not None and key in epoch.HISTORIC_SHA256:
            result["sha256"]=epoch.HISTORIC_SHA256[key]
        return result
    monkeypatch.setattr(m,"current_version",pinned)
    result=m.preflight(services)
    assert result["status"]=="ST_EPOCH3_READONLY_PREPARE_CHECK_PASS_NOT_DEPLOYMENT"
    assert result["aws_mutations"] is False
    assert result["deployment_authorized"] is False
    assert result["operator_preopen_inception_approval_recorded"] is False
    assert result["new_genesis_present"] is False
    assert result["prior_signal"]=="NOT_YET_ARCHIVED_WAIT_FOR_SCHEDULE"


def test_any_old_gap_written_is_blocked(monkeypatch):
    services,_=fake_services(occupied_gap=True)
    original=m.current_version
    monkeypatch.setattr(m,"current_version",lambda c,k,*,required:{
        **(original(c,k,required=required) or {}),
        **({"sha256":epoch.HISTORIC_SHA256[k]}
           if k in epoch.HISTORIC_SHA256 else {})
    } if (required or k=="paper/sessions/2026-11-05.json")
      else original(c,k,required=required))
    with pytest.raises(RuntimeError,match="OLD_BOOK_GAP_CHANGED"):
        m.preflight(services)


def test_prod_schedule_unexpectedly_enabled_is_blocked():
    services,_=fake_services(prod_enabled=True)
    with pytest.raises(RuntimeError,match="PRODUCTION_SCHEDULE_ENABLED"):
        m.preflight(services)


def test_old_signal_code_version_fail_closed():
    services,_=fake_services(signal_sha="wrong-SHA")
    with pytest.raises(RuntimeError,match="LATEST_ST_SIGNAL_PATCH_NOT_VERIFIED"):
        m.preflight(services)

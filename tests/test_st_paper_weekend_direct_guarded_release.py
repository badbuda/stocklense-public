"""Weekend ST-only direct Lambda update safety: fake AWS, no real network."""
from datetime import datetime, timezone
import io
from pathlib import Path

import pytest

from infra.aws import st_paper_weekend_direct_guarded_release as m


def saturday(hour):
    return datetime(2026, 11, 7, hour, 0, tzinfo=timezone.utc)


def sunday(hour):
    return datetime(2026, 11, 8, hour, 0, tzinfo=timezone.utc)


def test_weekend_guard_rejects_scheduled_hours_and_weekdays():
    assert m.window_ok(saturday(8))
    assert m.window_ok(sunday(21))
    assert not m.window_ok(saturday(3))
    assert not m.window_ok(sunday(23))
    assert not m.window_ok(datetime(2026, 11, 9, 15, tzinfo=timezone.utc))


def test_deploy_requires_both_explicit_approval_flags_before_aws():
    with pytest.raises(RuntimeError, match="EXPLICIT_"):
        m.apply_direct(None, approved=False, acknowledged=True)
    with pytest.raises(RuntimeError, match="EXPLICIT_"):
        m.apply_direct(None, approved=True, acknowledged=False)
    with pytest.raises(RuntimeError, match="WEEKEND_MAINTENANCE_WINDOW_ONLY"):
        m.apply_direct(None, approved=True, acknowledged=True, now=saturday(3))


def test_original_unsafe_changeset_must_be_exactly_15_known_resources():
    class CF:
        def __init__(self, overwrite=None):
            self.overwrite = overwrite
        def describe_change_set(self, **kw):
            assert kw["StackName"] == m.ST
            assert kw["ChangeSetName"] == m.ORIGINAL_CF_CHANGESET_NAME
            keys = sorted(m.RESOURCE_IDS)
            if self.overwrite == "extra":
                keys.append("PROD_SECRET_RESOURCE")
            if self.overwrite == "missing":
                keys.pop()
            return {"StackName":m.ST, "ChangeSetName":m.ORIGINAL_CF_CHANGESET_NAME,
                    "Status":"CREATE_COMPLETE","ExecutionStatus":"AVAILABLE",
                    "Changes":[{"ResourceChange":{"LogicalResourceId":k,
                                                  "Action":"Modify"}}
                               for k in keys]}
    assert m.unsafe_changeset_summary({"cloudformation":CF()})[
        "unsafe_resource_count"] == 15
    for option in ("extra", "missing"):
        with pytest.raises(RuntimeError, match="ORIGINAL_CHANGESET_CHANGED"):
            m.unsafe_changeset_summary({"cloudformation":CF(option)})


def make_state():
    names = {key: m.ST + "-" + key for key in m.ORDER}
    return {"st_outputs":names, "prod_schedules_all_disabled":True,
            "lambdas":{v:m.OLD for v in names.values()}}


def make_config(name, sha, revision="rev-old"):
    return {
        "FunctionArn":"arn:aws:lambda:eu-central-1:634740393398:function:" + name,
        "FunctionName":name, "Role":"arn:aws:iam::634740393398:role/stocklens-st-only",
        "Runtime":"python3.11","Handler":"infra.aws.independent_paper.handler",
        "PackageType":"Zip","CodeSha256":sha,"RevisionId":revision,
        "Version":"$LATEST", "LastUpdateStatus":"Successful","State":"Active",
        "MemorySize":512,"Timeout":120,
    }


class FakeLambda:
    def __init__(self, fail_dryrun=False):
        self.codes={m.ST+"-"+k:m.OLD for k in m.ORDER}
        self.revisions={k:"rev-old" for k in self.codes}
        self.real_updates=[]
        self.dryruns=[]
        self.fail_dryrun=fail_dryrun

    def get_function_configuration(self, *, FunctionName):
        return make_config(FunctionName,self.codes[FunctionName],
                           self.revisions[FunctionName])

    def update_function_code(self, **kwargs):
        fn=kwargs["FunctionName"]
        assert fn in self.codes
        assert kwargs["S3Bucket"]==m.p.ST_BUCKET
        assert kwargs["S3ObjectVersion"]=="versioned-xyz"
        assert kwargs["S3Key"]==m.artifact_key()
        assert kwargs["Publish"] is False
        assert kwargs["RevisionId"]==self.revisions[fn]
        if kwargs.get("DryRun") is True:
            self.dryruns.append(fn)
            if self.fail_dryrun and len(self.dryruns)==3:
                raise RuntimeError("DRY_RUN_DENIED")
            return {"StatusCode":204}
        assert "DryRun" not in kwargs
        self.real_updates.append(fn)
        self.codes[fn]=m.NEW
        self.revisions[fn]="rev-new"
        return {"CodeSha256":m.NEW}


class FakeCF:
    def __init__(self):
        self.deleted=[]
    def delete_change_set(self, **kwargs):
        assert kwargs == {"StackName":m.ST,
                          "ChangeSetName":m.ORIGINAL_CF_CHANGESET_NAME}
        self.deleted.append(kwargs)
    def __getattr__(self,name):
        raise AssertionError("UNEXPECTED_CFN_MUTATION:" + name)


def patch_services(monkeypatch, fail_dryrun=False):
    sdk={"lambda":FakeLambda(fail_dryrun),"cloudformation":FakeCF()}
    state=make_state()
    state["st_outputs"] = {k:m.ST+"-"+k for k in m.ORDER}
    monkeypatch.setattr(m,"trusted_inventory",lambda c:(
        state, {fn:sdk["lambda"].get_function_configuration(FunctionName=fn)
                for fn in state["lambdas"]},
        {"CandidateSignalOnlyRuleName":True,
         "CandidatePaperOnlyRuleName":True,
         "CandidateOrchestratorRuleName":True,
         "CandidateSessionWatchdogSchedule":True},
    ))
    monkeypatch.setattr(m,"unsafe_changeset_summary",lambda c:{
        "name":m.ORIGINAL_CF_CHANGESET_NAME,"unsafe_resource_count":15,
    })
    monkeypatch.setattr(m.g,"candidate_bytes",lambda : b"fixed-candidate")
    monkeypatch.setattr(m.g,"digest",lambda x: m.NEW)
    monkeypatch.setattr(m.g,"verify_staged_artifact",lambda c,s:{
        "artifact_sha256_verified":True})
    monkeypatch.setattr(m,"ensure_versioned_st_artifact",lambda c,p:{
        "bucket":m.p.ST_BUCKET,"key":m.artifact_key(),"version":"versioned-xyz",
    })
    return sdk


def test_deploy_verifies_all_five_dry_runs_first_then_updates_without_cfn(monkeypatch):
    sdk=patch_services(monkeypatch)
    result=m.apply_direct(sdk,approved=True,acknowledged=True,now=saturday(11),
                          sleep=lambda _:None)
    assert result["status"] == "ST_ONLY_FIVE_LAMBDA_CODES_DEPLOYED_AND_VERIFIED"
    assert result["paper_2026_11_05"]=="MISSING_NEVER_REPLAYED"
    assert result["prod_schedules_all_disabled"] is True
    assert len(sdk["lambda"].dryruns)==5
    assert len(sdk["lambda"].real_updates)==5
    assert sdk["lambda"].real_updates[-1] == m.ST+"-CandidatePaperFunctionName"
    assert len(sdk["cloudformation"].deleted)==1
    assert all(sha==m.NEW for sha in sdk["lambda"].codes.values())


def test_failed_dry_run_never_deletes_cfn_set_or_updates_lambda(monkeypatch):
    sdk=patch_services(monkeypatch,fail_dryrun=True)
    with pytest.raises(RuntimeError,match="DRY_RUN_DENIED"):
        m.apply_direct(sdk,approved=True,acknowledged=True,now=saturday(11))
    assert sdk["lambda"].real_updates==[]
    assert sdk["cloudformation"].deleted==[]


def test_missing_schedule_target_is_hard_stop():
    functions={m.ST+"-paper-candidate":make_config(m.ST+"-paper-candidate",m.OLD)}
    class E:
        def list_targets_by_rule(self, **kwargs):
            return {"Targets":[{"Arn":"arn:aws:lambda:eu-central-1:634740393398:function:prod"}]}
    state={"st_outputs":{
        "CandidateSignalOnlyRuleName":"signal-rule",
        "CandidateFunctionName":m.ST+"-paper-candidate",
    }}
    with pytest.raises(RuntimeError,match="ST_SCHEDULE_TARGET_DIFFERS"):
        m.verify_event_targets({"events":E()},state,functions)


def test_source_contains_no_broker_or_cfn_stack_mutators():
    text=Path("infra/aws/st_paper_weekend_direct_guarded_release.py").read_text()
    for forbidden in (
        ".execute_change_set(", ".update_stack(",
        ".update_function_configuration(", ".enable_rule(", ".disable_rule(",
        ".invoke(", ".set_alarm_state(", ".put_metric_alarm(",
        ".put_item(", ".delete_object(", ".delete_stack(",
    ):
        assert forbidden not in text
    assert "RevisionId=last" in text
    assert 'DryRun=True' in text
    assert "S3ObjectVersion" in text
    assert "delete_change_set" in text

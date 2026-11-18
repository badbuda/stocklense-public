"""ST Paper blocker diagnostic shows ALL causes without mutating AWS."""
from __future__ import annotations
import io
import json
from types import SimpleNamespace

import pytest
from infra.aws import st_paper_operational_blockers_readonly as mod


def mock_cloud(*, paper_enabled=False, prod_enabled=False, continuity=False,
               signal_present=True, wrong_account=False, version_missing=False):
    calls = []
    st = {"CandidateDataBucket": mod.BUCKET}
    prod = {"CandidateDataBucket": mod.PROD_BUCKET}
    for i, key in enumerate(mod.RULE_KEYS):
        st[key] = "st-" + str(i)
        prod[key] = "prod-" + str(i)
    def stack(StackName):
        out = st if StackName == mod.ST else prod
        return {"Stacks": [{"StackStatus": "CREATE_COMPLETE",
                            "Outputs": [{"OutputKey": k, "OutputValue": v}
                                        for k, v in out.items()]}]}
    def drule(Name):
        number = int(Name[-1])
        isprod = Name.startswith("prod")
        return {"State": ("ENABLED" if prod_enabled and isprod
                          else "DISABLED" if isprod
                          else "ENABLED" if number == 0 or (number == 1 and paper_enabled)
                          else "DISABLED"),
                "ScheduleExpression": (mod.EXPECTED_PROD_CRON if isprod
                                       else mod.EXPECTED_ST_CRON)[number]}
    def obj(Bucket, Key):
        if (Key.startswith("paper/continuity/") and not continuity or
            Key.startswith("signals/") and not signal_present):
            e = RuntimeError("NoSuchKey")
            e.response = {"Error": {"Code": "NoSuchKey"}}
            raise e
        raw = json.dumps({"test_record": True}).encode()
        return {"VersionId": "v1", "ContentLength": len(raw),
                "Body": io.BytesIO(raw)}
    st["CandidateFunctionName"] = "st-signal"
    st["CandidatePaperFunctionName"] = "st-paper"
    def version_list(**kwargs):
        is_continuity = "continuity" in kwargs["Prefix"]
        should_be_missing = version_missing or (is_continuity and not continuity)
        return {"Versions": ([] if should_be_missing else
                             [{"Key": kwargs["Prefix"], "VersionId": "v1",
                               "IsLatest": True}]), "IsTruncated": False}
    services = {
        "sts": SimpleNamespace(get_caller_identity=lambda: {
            "Account": "WRONG" if wrong_account else mod.ACCOUNT}),
        "cloudformation": SimpleNamespace(describe_stacks=stack),
        "events": SimpleNamespace(describe_rule=drule),
        "s3": SimpleNamespace(get_bucket_versioning=lambda **kw: {"Status": "Enabled"},
                              get_object=obj, list_object_versions=version_list),
        "lambda": SimpleNamespace(
            get_function_configuration=lambda FunctionName: {
                "FunctionName": FunctionName, "State": "Active",
                "LastUpdateStatus": "Successful",
                "Handler": ("infra.aws.independent_paper.handler"
                            if FunctionName == "st-paper"
                            else "infra.aws.independent_pipeline.handler"),
                "CodeSha256": "K" * 44, "LastModified": "2026-11-10T06:58:35Z",
                "Environment": {"Variables": {"STOCKLENS_DATA_BUCKET": mod.BUCKET}},
            }),
        "cloudwatch": SimpleNamespace(describe_alarms=lambda **kw:
                       {"MetricAlarms": [
                           {"AlarmName": "stocklens-st-MissedSessions", "StateValue": "ALARM"},
                           {"AlarmName": "stocklens-st-WatchdogFailClosed", "StateValue": "ALARM"}]}),
    }
    return services, calls


def test_disabled_paper_and_missing_continuity_both_visible():
    c, _ = mock_cloud()
    out = mod.diagnostic(c, "2026-11-17")
    assert out["status"] == "BLOCKED_WITH_INDEPENDENT_OBSERVATIONS"
    assert "ST_PAPER_RULE_NOT_ENABLED" in out["blockers"]
    assert "ST_CONTINUITY_MISSING_VERIFIED" in out["blockers"]
    assert "ST_ALARMS_NON_OK:2" in out["blockers"]
    assert out["aws_mutations"] is False
    assert out["lambda_invocations"] is False
    assert out["no_paper_chain_attestation_performed"] is True


def test_prod_schedule_drift_and_signal_absence_reported_together():
    c, _ = mock_cloud(prod_enabled=True, signal_present=False)
    out = mod.diagnostic(c, "2026-11-17")
    assert "PROD_RULE_NOT_DISABLED:" + mod.RULE_KEYS[0] in out["blockers"]
    assert "ST_SIGNAL_MISSING_VERIFIED" in out["blockers"]


def test_no_obvious_blockers_never_claims_paper_pass():
    c, _ = mock_cloud(paper_enabled=True, continuity=True)
    c["cloudwatch"] = SimpleNamespace(describe_alarms=lambda **kw:
                   {"MetricAlarms": [{"AlarmName": "stocklens-st-test",
                                      "StateValue": "OK"}]})
    out = mod.diagnostic(c, "2026-11-17")
    assert out["blockers"] == []
    assert out["status"] == "NO_OBVIOUS_BLOCKERS_NOT_PAPER_ACCEPTANCE"
    assert out["no_paper_chain_attestation_performed"] is True


def test_wrong_account_rejected_before_any_stacks():
    c, _ = mock_cloud(wrong_account=True)
    c["cloudformation"] = SimpleNamespace(
        describe_stacks=lambda **kw: pytest.fail("attempted wrong account AWS access"))
    with pytest.raises(RuntimeError, match="WRONG_ACCOUNT_STOP_ALL"):
        mod.diagnostic(c, "2026-11-17")


def test_version_inventory_proves_missing_without_listbucket():
    c, _ = mock_cloud()
    def access_denied(**kw):
        if "paper/" in kw["Key"]:
            err = RuntimeError("403")
            err.response = {"Error": {"Code": "AccessDenied"}}
            raise err
        raw = json.dumps({"source": True}).encode()
        return {"VersionId": "v1", "ContentLength": len(raw), "Body": io.BytesIO(raw)}
    c["s3"].get_object = access_denied
    out = mod.diagnostic(c, "2026-11-17")
    assert out["s3_objects"]["continuity"]["status"] == (
        "MISSING_VERIFIED_BY_VERSION_INVENTORY")
    assert "ST_CONTINUITY_MISSING_VERIFIED_BY_VERSION_INVENTORY" in out["blockers"]
    assert out["aws_mutations"] is False


def test_live_runtime_config_and_sha_are_reported_without_lambda_invoke():
    c, _ = mock_cloud()
    out = mod.diagnostic(c, "2026-11-17")
    assert out["runtime_lambdas"]["paper"]["state"] == "Active"
    assert out["runtime_lambdas"]["paper"]["handler_matches"] is True
    assert out["runtime_lambdas"]["signal"]["bucket_matches"] is True
    assert out["lambda_invocations"] is False

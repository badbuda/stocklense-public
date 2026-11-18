"""ST Paper blocker diagnostic shows ALL causes without mutating AWS."""
from __future__ import annotations
import io
import json
from types import SimpleNamespace

import pytest
from infra.aws import st_paper_operational_blockers_readonly as mod


def mock_cloud(*, paper_enabled=False, prod_enabled=False, continuity=False,
               signal_present=True, wrong_account=False):
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
    services = {
        "sts": SimpleNamespace(get_caller_identity=lambda: {
            "Account": "WRONG" if wrong_account else mod.ACCOUNT}),
        "cloudformation": SimpleNamespace(describe_stacks=stack),
        "events": SimpleNamespace(describe_rule=drule),
        "s3": SimpleNamespace(get_bucket_versioning=lambda **kw: {"Status": "Enabled"},
                              get_object=obj),
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

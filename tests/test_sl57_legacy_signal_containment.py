"""Deterministic fail-closed regression for legacy ST-only Signal containment."""
import io
import json
from types import SimpleNamespace
import pytest
from infra.aws import sl57_legacy_signal_containment as m


def fake(*, prod_enabled=False, st_source=True, errors=True):
    changes = []
    stacks = {}
    for name, func, bucket in (
        (m.ST, m.ST_SIGNAL, m.ST_BUCKET),
        (m.LEGACY, m.LEGACY_SIGNAL, "stocklens-independent-staging-candidatedata"),
        (m.PROD, "stocklens-prod-candidate", m.PROD_BUCKET),
    ):
        outputs = {"CandidateFunctionName": func, "CandidateDataBucket": bucket}
        for k in m.RULE_KEYS:
            outputs[k] = name + "-" + k
        stacks[name] = outputs

    def dstack(StackName):
        return {"Stacks": [{"StackStatus": "CREATE_COMPLETE",
            "Outputs": [{"OutputKey": k, "OutputValue": v}
                        for k, v in stacks[StackName].items()]}]}

    def drule(Name):
        name, key = Name.split("-Candidate", 1)
        key = "Candidate" + key
        state = "DISABLED" if name == m.PROD else "ENABLED"
        if name == m.PROD and prod_enabled:
            state = "ENABLED"
        if Name in changes:
            state = "DISABLED"
        cron = (m.OLD_SIGNAL_CRON if name == m.LEGACY else m.ST_SIGNAL_CRON)
        return {"State": state, "ScheduleExpression": cron}

    def target(Rule):
        name = Rule.split("-Candidate", 1)[0]
        return {"Targets": [{"Arn": "arn:" + name + "-signal"}]}

    def cfg(FunctionName):
        name = m.ST if FunctionName == m.ST_SIGNAL else m.LEGACY
        bucket = stacks[name]["CandidateDataBucket"]
        return {"State": "Active", "LastUpdateStatus": "Successful",
                "Handler": "infra.aws.independent_pipeline.handler",
                "CodeSha256": "a" * 30, "FunctionArn": "arn:" + name + "-signal",
                "Environment": {"Variables": {"STOCKLENS_DATA_BUCKET": bucket}}}

    doc = {"mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
           "latest": {"asof_date": m.PROOF_SESSION if st_source else "2026-11-16"},
           "execution_plan": {"broker_actions_enabled": False}}
    raw = json.dumps(doc).encode()
    def get_object(**kwargs):
        return {"VersionId": "v-1", "ContentLength": len(raw),
                "Body": io.BytesIO(raw)}

    def log(**kwargs):
        if not errors:
            return {"events": []}
        needle = next((s for start, end, s in m.ERROR_PROOFS
                       if start.startswith("2026-11-17")
                       == (kwargs["startTime"] == int(__import__("datetime").datetime.fromisoformat(
                          m.ERROR_PROOFS[0][0]).timestamp() * 1000))), "")
        return {"events": [{"message": needle}]}

    c = {
        "sts": SimpleNamespace(get_caller_identity=lambda: {"Account": m.ACCOUNT}),
        "cloudformation": SimpleNamespace(describe_stacks=dstack),
        "events": SimpleNamespace(describe_rule=drule,
                     list_targets_by_rule=target,
                     disable_rule=lambda Name: changes.append(Name)),
        "lambda": SimpleNamespace(get_function_configuration=cfg),
        "s3": SimpleNamespace(
            get_bucket_versioning=lambda **kw: {"Status": "Enabled"},
            get_object=get_object),
        "logs": SimpleNamespace(filter_log_events=log),
    }
    return c, changes, stacks


def test_inspect_is_read_only_and_evidence_bound():
    c, changes, _ = fake()
    out = m.run(c, "inspect")
    assert out["status"] == "ST_ONLY_LEGACY_SIGNAL_PAUSE_ELIGIBLE_NOT_EXECUTED"
    assert out["st_verified_signal"]["session"] == "2026-11-17"
    assert out["aws_mutations"] is False
    assert changes == []


def test_pause_requires_explicit_approval_and_disables_only_old_signal():
    c, changes, stacks = fake()
    with pytest.raises(RuntimeError, match="EXPLICIT_OPERATOR_APPROVAL_REQUIRED"):
        m.run(c, "pause", approved=False)
    assert changes == []
    out = m.run(c, "pause", approved=True)
    assert out["status"] == "LEGACY_STAGING_SIGNAL_SCHEDULE_PAUSED_NOT_PAPER_RECOVERY"
    assert changes == [stacks[m.LEGACY]["CandidateSignalOnlyRuleName"]]
    assert out["alarms_untouched"] and out["paper_and_watchdog_untouched"]


@pytest.mark.parametrize("kwargs,reason", [
    ({"prod_enabled": True}, "PROD_SCHEDULE_MUST_REMAIN_DISABLED"),
    ({"st_source": False}, "ST_SIGNAL_NOT_QUALIFIED_OR_BROKER_UNSAFE"),
    ({"errors": False}, "OLD_LEGACY_VENDOR_LAG_LOG_NOT_PROVEN"),
])
def test_failure_blocks_mutation(kwargs, reason):
    c, changes, _ = fake(**kwargs)
    with pytest.raises(RuntimeError, match=reason):
        m.run(c, "pause", approved=True)
    assert changes == []


def test_wrong_account_denied_before_any_stack_read():
    c, changes, _ = fake()
    c["sts"] = SimpleNamespace(get_caller_identity=lambda: {"Account": "wrong"})
    c["cloudformation"] = SimpleNamespace(
        describe_stacks=lambda **kwargs: pytest.fail("stack access on wrong account"))
    with pytest.raises(RuntimeError, match="WRONG_ACCOUNT"):
        m.run(c, "inspect")
    assert changes == []

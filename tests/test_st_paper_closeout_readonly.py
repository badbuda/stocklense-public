"""ST acceptance must fail closed and never authorize broker or PROD writes."""
import io
import json
from types import SimpleNamespace

import pytest
from infra.aws import st_paper_closeout_readonly as mod


def service_mocks(*, prod_enabled=False, paper_enabled=True, continuity=True):
    names = ("CandidateSignalOnlyRuleName", "CandidatePaperOnlyRuleName",
             "CandidateOrchestratorRuleName")
    st = {"CandidateDataBucket": mod.BUCKET,
          "CandidatePaperFunctionName": "st-paper",
          "CandidateFunctionName": "st-signal",
          "CandidateAlertsTopic": "arn:aws:sns:eu-central-1:634740393398:stocklens-st-candidate-alerts"}
    prod = {"CandidateDataBucket": mod.PROD_BUCKET}
    for i, name in enumerate(names):
        st[name] = "st-" + str(i)
        prod[name] = "prod-" + str(i)
    def describe_stacks(StackName):
        out = st if StackName == mod.ST else prod
        return {"Stacks": [{"StackStatus": "CREATE_COMPLETE",
                            "Outputs": [{"OutputKey": k, "OutputValue": v}
                                        for k, v in out.items()]}]}
    def describe_rule(Name):
        idx = int(Name[-1])
        cron = (mod.SIGNAL_CRON, mod.PAPER_CRON, mod.ORCHESTRATOR_CRON)[idx]
        state = ("ENABLED" if idx == 0 or (idx == 1 and paper_enabled) else "DISABLED")
        if Name.startswith("prod-"):
            state = "ENABLED" if prod_enabled and idx == 1 else "DISABLED"
        return {"State": state, "ScheduleExpression": cron}
    source = {"status": "STAGING_PAPER_SCHEDULE_READINESS_PASS_READ_ONLY",
              "session": "2026-11-02", "genesis_session": mod.GENESIS,
              "chain_sessions": 2, "continuity_status": "ON_TIME_QUALIFIED",
              "broker_actions": False, "broker_orders": False, "broker_fills": False,
              "paper_data_written": False, "paper_version_id": "p-v2",
              "paper_sha256": "a" * 64}
    if not continuity:
        source["continuity_status"] = "HALTED"
    calls = []
    def invoke(**kwargs):
        event = json.loads(kwargs["Payload"])
        assert event == {"mode": "STAGING_PAPER_SCHEDULE_READINESS",
                         "expected_session": "2026-11-02", "bootstrap": False}
        calls.append("readiness")
        return {"StatusCode": 200, "Payload": io.BytesIO(json.dumps(source).encode())}
    return {
        "sts": SimpleNamespace(get_caller_identity=lambda: {"Account": mod.ACCOUNT}),
        "cloudformation": SimpleNamespace(describe_stacks=describe_stacks),
        "events": SimpleNamespace(
            describe_rule=describe_rule,
            list_targets_by_rule=lambda Rule: {"Targets": [{
                "Arn": "arn:st-paper" if Rule == "st-1" else "arn:st-signal"}]}),
        "s3": SimpleNamespace(get_bucket_versioning=lambda **_: {"Status": "Enabled"}),
        "cloudwatch": SimpleNamespace(describe_alarms=lambda **_:
                                     {"MetricAlarms": [{
                                         "AlarmName": "st-watchdog", "StateValue": "OK",
                                         "ActionsEnabled": True,
                                         "AlarmActions": [st["CandidateAlertsTopic"]]}]}),
        "sns": SimpleNamespace(list_subscriptions_by_topic=lambda **_:
                               {"Subscriptions": [{"Protocol": "email", "SubscriptionArn": "confirmed"}]}),
        "lambda": SimpleNamespace(
            get_function_configuration=lambda FunctionName: {
                "State": "Active", "LastUpdateStatus": "Successful",
                "FunctionArn": "arn:st-paper" if FunctionName == "st-paper" else "arn:st-signal",
                "Environment": {"Variables": {"STOCKLENS_DATA_BUCKET": mod.BUCKET}}},
            invoke=invoke)
    }, calls


def test_verified_modeled_st_paper_is_not_broker_execution(monkeypatch):
    svc, calls = service_mocks()
    def read(_, key, *, version=None):
        if key.startswith("signals/"):
            return ({"mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
                     "latest": {"asof_date": "2026-11-02"},
                     "execution_plan": {"broker_actions_enabled": False}},
                    "s-v1", "b" * 64)
        assert key == "paper/example.json" and version == "p-v2"
        return ({"mode": "MODELED"}, "p-v2", "a" * 64)
    monkeypatch.setattr(mod, "read_versioned_json", read)
    monkeypatch.setattr(mod, "receipt_key_for_version", lambda *x: "paper/example.json")
    report = mod.audit(svc, "2026-11-02")
    assert report["status"] == "ST_READ_ONLY_ACCEPTANCE_PASS_MODELED_ONLY"
    assert report["paper_sessions"] == 2
    assert report["broker_orders"] is False
    assert report["aws_mutations"] is False
    assert calls == ["readiness"]


@pytest.mark.parametrize("options,expected", [
    ({"prod_enabled": True}, "PROD_RULE_ACTIVE"),
    ({"paper_enabled": False}, "ST_RECURRING_PAPER_SCHEDULE_DISABLED"),
    ({"continuity": False}, "PAPER_READINESS_NOT_QUALIFIED"),
])
def test_fail_closed_no_broker_mutations(monkeypatch, options, expected):
    svc, _ = service_mocks(**options)
    monkeypatch.setattr(mod, "read_versioned_json", lambda *_a, **_k: (
        {"mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
         "latest": {"asof_date": "2026-11-02"},
         "execution_plan": {"broker_actions_enabled": False}}, "v1", "b" * 64))
    with pytest.raises(RuntimeError, match=expected):
        mod.audit(svc, "2026-11-02")


def test_wrong_account_refused_before_any_stack_lookup():
    svc, _ = service_mocks()
    svc["sts"] = SimpleNamespace(get_caller_identity=lambda: {"Account": "wrong"})
    svc["cloudformation"] = SimpleNamespace(describe_stacks=lambda **_:
                                            pytest.fail("no AWS reads after wrong account"))
    with pytest.raises(RuntimeError, match="WRONG_AWS_ACCOUNT"):
        mod.audit(svc, "2026-11-02")

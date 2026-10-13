"""Regression tests written against PR #78 head 97c9108 BEFORE the fix.
Each test reproduces a defect; all must fail on 97c9108 and pass after the patch."""
from datetime import datetime, timezone
import io, json, pathlib
import pytest

from infra.aws.independent_orchestrator import run_orchestrator


class BrokerLeak:
    """Paper/Signal Lambda that reports an unauthorized broker flag."""
    def __init__(self, leak_key, where):
        self.leak_key, self.where, self.calls = leak_key, where, []

    def invoke(self, **kw):
        ev = json.loads(kw["Payload"]); fn = kw["FunctionName"]
        self.calls.append(fn)
        status = "STAGED_SIGNAL_ARCHIVED" if fn == "signal" else "STAGED_PAPER_CATCHUP_COMPLETED"
        out = {"status": status, "session": ev["expected_session"],
               "broker_actions": False, "broker_orders": False, "broker_fills": False,
               "signal_sha256": "a" * 64, "paper_sha256": "b" * 64, "sessions": []}
        if fn == self.where:
            out[self.leak_key] = True
        return {"StatusCode": 200, "Payload": io.BytesIO(json.dumps(out).encode())}


NOW = datetime(2026, 10, 13, 0, 10, tzinfo=timezone.utc)


@pytest.mark.parametrize("key", ["broker_actions", "broker_orders", "broker_fills"])
@pytest.mark.parametrize("where", ["signal", "paper"])
def test_any_true_broker_flag_fails_closed(key, where):
    with pytest.raises(RuntimeError, match="UNSAFE_CANDIDATE_RESPONSE"):
        run_orchestrator(now=NOW, client=BrokerLeak(key, where),
                         signal_function="signal", paper_function="paper")


def test_staging_template_has_failure_routing_and_calendar_watchdog():
    t = pathlib.Path("infra/aws/independent-staging.yaml").read_text()
    for needed in ("AWS::Lambda::EventInvokeConfig", "OnFailure", "AWS::SNS::Topic",
                   "AWS::CloudWatch::Alarm", "MissedSessions",
                   "CandidateSessionWatchdogLambda", "EXPECTED_SCHEDULER_STATE",
                   "MetricName: InvalidReceipts", "MetricName: ConfigurationError",
                   "MetricName: WatchdogFailClosed", "paper/book/*"):
        assert needed in t, needed
    # the trading orchestrator schedule must stay DISABLED in staging
    i = t.index("CandidateOrchestratorSchedule:")
    assert "State: DISABLED" in t[i:i + 600]


def test_every_watchdog_metric_except_heartbeat_has_an_alarm():
    """FAIL_CLOSED must never be visible only in logs."""
    from datetime import datetime, timezone
    from infra.aws.independent_session_watchdog import inspect
    t = pathlib.Path("infra/aws/independent-staging.yaml").read_text()
    r = inspect(now=datetime(2026, 10, 15, tzinfo=timezone.utc), rule_state="ENABLED",
                expected_rule_state="ENABLED", monitoring_start=None, read_record=lambda s: None)
    for metric in r["metrics"]:
        assert f"MetricName: {metric}" in t, metric


def test_alert_topic_uses_cloudwatch_usable_customer_managed_key():
    import yaml
    class L(yaml.SafeLoader):
        pass
    L.add_multi_constructor("!", lambda loader, suffix, node: suffix + ":" + str(node.value))
    doc = yaml.load(pathlib.Path("infra/aws/independent-staging.yaml").read_text(), Loader=L)
    r = doc["Resources"]
    assert r["CandidateAlerts"]["Properties"]["KmsMasterKeyId"] == "GetAtt:CandidateAlertsKey.Arn"
    key = r["CandidateAlertsKey"]
    assert key["Type"] == "AWS::KMS::Key" and key["Properties"]["EnableKeyRotation"] is True
    cw = [st for st in key["Properties"]["KeyPolicy"]["Statement"]
          if st.get("Principal", {}).get("Service") == "cloudwatch.amazonaws.com"]
    assert cw and {"kms:GenerateDataKey*", "kms:Decrypt"} <= set(cw[0]["Action"])
    assert "aws:SourceAccount" in cw[0]["Condition"]["StringEquals"]


def test_all_staging_receipt_readers_can_distinguish_missing_s3_keys():
    """Regression for live AccessDenied on signal's first absent S3 GetObject.

    Missing GetObject requires ListBucket on the bucket itself, not only a
    ListObjects-specific s3:prefix condition. Object read/write access stays
    restricted to the existing candidate prefixes; no other bucket is granted.
    """
    import yaml

    class CloudFormationLoader(yaml.SafeLoader):
        pass

    CloudFormationLoader.add_multi_constructor(
        "!", lambda loader, suffix, node: suffix + ":" + str(node.value)
    )
    doc = yaml.load(
        pathlib.Path("infra/aws/independent-staging.yaml").read_text(),
        Loader=CloudFormationLoader,
    )
    resources = doc["Resources"]
    for role_name in ("CandidateRole", "CandidatePaperRole", "CandidateSessionWatchdogRole"):
        role = resources[role_name]
        statements = [
            statement
            for policy in role["Properties"]["Policies"]
            for statement in policy["PolicyDocument"]["Statement"]
        ]
        list_grants = [
            statement for statement in statements
            if "s3:ListBucket" in (
                statement["Action"] if isinstance(statement["Action"], list)
                else [statement["Action"]]
            )
        ]
        assert len(list_grants) == 1, role_name
        grant = list_grants[0]
        assert grant["Effect"] == "Allow", role_name
        assert grant["Resource"] == "GetAtt:CandidateData.Arn", role_name
        assert "Condition" not in grant, role_name

    orchestrator = resources["CandidateOrchestratorSchedule"]["Properties"]
    assert orchestrator["State"] == "DISABLED"

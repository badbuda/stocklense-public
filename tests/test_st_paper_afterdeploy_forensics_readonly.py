"""No-AWS-mutations ST afterdeploy evidence triage."""
from datetime import datetime,timezone
from pathlib import Path
import pytest
from infra.aws import st_paper_afterdeploy_forensics_readonly as m


class AwsException(Exception):
    def __init__(self, code):
        self.response={"Error":{"Code":code}}


def test_s3_head_requires_actual_version_id():
    class S3:
        def head_object(self,**kwargs):
            assert kwargs["Bucket"]==m.BUCKET
            return {"VersionId":"abc","ContentLength":42}
    result=m.s3_head(S3(),"signals/2026-11-05.json")
    assert result["status"]=="VERSIONED_PRESENT_NOT_PAPER_ATTESTATION"
    assert result["version_id_present"] is True


@pytest.mark.parametrize("status,expected",[
    ("404","NOT_FOUND_AT_PROBED_KEY"),
    ("403","ACCESS_DENIED_UNVERIFIED"),
    ("ThrottlingException","READ_ERROR")
])
def test_s3_missing_denied_and_transient_errors_never_count_as_receipt(status,expected):
    class S3:
        def head_object(self,**kwargs):
            raise AwsException(status)
    assert m.s3_head(S3(),"paper/continuity/2026-11-05.json")["status"]==expected


def test_inventory_uses_exact_version_id_and_never_fabricates_ledger():
    class S3:
        def list_object_versions(self,**kwargs):
            return {"Versions":[
                {"Key":"paper/ledger/2026-11-05.json","VersionId":"v1","IsLatest":True},
                {"Key":"paper/ledger/2026-11-06.json","VersionId":"v2","IsLatest":False},
                {"Key":"paper/ledger/2026-11-06.json","VersionId":"v3","IsLatest":True},
                {"Key":"paper/book/genesis.json","VersionId":"v4","IsLatest":True},
            ],"IsTruncated":False}
    result=m.paper_version_inventory(S3(),["2026-11-05","2026-11-06"])
    assert result["status"]=="COMPLETE_PREFIX_INVENTORY_NOT_LEDGER_ATTESTATION"
    assert len(result["matches_by_session"]["2026-11-05"])==1
    assert len(result["matches_by_session"]["2026-11-06"])==1
    assert result["matches_by_session"]["2026-11-06"][0]["key"]=="paper/ledger/2026-11-06.json"


def test_inventory_incomplete_pagination_cannot_be_trusted():
    class S3:
        def list_object_versions(self,**kwargs):
            return {"Versions":[],"IsTruncated":True}
    assert m.paper_version_inventory(S3(),["2026-11-05"])["status"]=="PAGINATION_INCOMPLETE_UNVERIFIED"


def test_logs_strip_raw_content_and_only_emit_known_markers():
    class Logs:
        def filter_log_events(self,**kwargs):
            return {"events":[{
                "timestamp":1794000000000,
                "message":"TOKEN=DO_NOT_PRINT SESSION_WITHOUT_CONTINUITY_RECORD:2026-11-05"
            }]}
    output=m.log_markers(Logs(),m.WATCHDOG_GROUP,0)
    assert output["error_marker_count"]==1
    assert "SESSION_WITHOUT_CONTINUITY_RECORD" in output["last_error_markers"][0]["markers"]
    assert "TOKEN=" not in str(output)


def test_alarm_snapshot_never_claims_all_ok_if_no_alarms():
    class CW:
        def describe_alarms(self,**kwargs):
            return {"MetricAlarms":[]}
    result=m.alarms_snapshot(CW())
    assert result["all_ok"] is False


def test_full_inspection_cannot_attest_to_paper_book(monkeypatch):
    class S3:
        def get_bucket_versioning(self,**kwargs):
            return {"Status":"Enabled"}
        def head_object(self,**kwargs):
            raise AwsException("404")
        def list_object_versions(self,**kwargs):
            return {"Versions":[],"IsTruncated":False}
    class CW:
        def describe_alarms(self,**kwargs):
            return {"MetricAlarms":[{"AlarmName":"stocklens-st-MissedSessionsAlarm",
                                      "StateValue":"ALARM",
                                      "Namespace":"StockLens/IsolatedST"}]}
    class Logs:
        def filter_log_events(self,**kwargs):
            return {"events":[]}
    monkeypatch.setattr(m.release,"check_readonly",lambda c:{
        "current_all_candidate":True,"mixed_or_partial_code":False,
        "prod_schedules_all_disabled":True,
        "blocked_cfn_change_set":{"status":"RETIRED_NOT_EXECUTED"},
        "st_rule_targets_verified":{"CandidateSignalOnlyRuleName":True},
    })
    data=m.inspect({"s3":S3(),"cloudwatch":CW(),"logs":Logs()},
                   ["2026-11-05","2026-11-06"],
                   now=datetime(2026,11,7,16,tzinfo=timezone.utc))
    assert data["release"]["all_five_candidate"] is True
    assert data["alarms"]["all_ok"] is False
    assert data["paper_ledger_acceptance"]=="NOT_PROVEN_BY_THIS_READ_ONLY_DIAGNOSTIC"
    assert data["aws_mutations"] is False
    assert data["lambda_invocations"] is False
    assert data["paper_backfill"] is False


def test_release_not_verified_is_blocked(monkeypatch):
    monkeypatch.setattr(m.release,"check_readonly",lambda c:{
        "current_all_candidate":False,"mixed_or_partial_code":True,
        "prod_schedules_all_disabled":True,
        "blocked_cfn_change_set":{"status":"RETIRED_NOT_EXECUTED"}})
    with pytest.raises(RuntimeError,match="ST_RELEASE_NOT_FULLY_VERIFIED"):
        m.inspect({},["2026-11-05"])


def test_diagnostic_source_has_no_aws_or_broker_mutators():
    source=Path("infra/aws/st_paper_afterdeploy_forensics_readonly.py").read_text()
    forbidden=(".invoke(", ".put_object(", ".delete_object(", ".set_alarm_state(",
               ".execute_change_set(", ".delete_change_set(", ".update_function_code(",
               ".update_stack(", ".enable_rule(", ".disable_rule(", ".put_metric_alarm(")
    assert all(item not in source for item in forbidden)

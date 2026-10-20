"""Read-only staging operator snapshot and lifetime watchdog regression."""
from datetime import datetime, timezone
from pathlib import Path

import pytest

from infra.aws.staging_readonly_status import (
    _session_status, snapshot, StagingDiagnosticError,
)


def U(y, m, d, h, minute=0):
    return datetime(y, m, d, h, minute, tzinfo=timezone.utc)


def _payload(day):
    return {
        "mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
        "signal_source": "QQQ_ADJUSTED_DAILY_CLOSE",
        "latest": {"asof_date": day},
        "data_audit": {"last_completed_date": day,
                       "source": "YFINANCE_QQQ_AUTO_ADJUSTED"},
        "execution_plan": {"broker_actions_enabled": False},
    }


def test_session_without_receipt_is_pending_then_durable_missing():
    assert _session_status(now=U(2026, 10, 21, 2, 59),
                           session="2026-10-20", bucket="private", head=None
                           )["status"] == "NOT_DUE_NO_RECEIPT"
    assert _session_status(now=U(2026, 10, 21, 3, 30),
                           session="2026-10-20", bucket="private", head=None
                           )["status"] == "MISSING_DUE_RECEIPT"


def test_versioned_genuine_receipt_on_time_and_late_classified_separately():
    import json
    raw = json.dumps(_payload("2026-10-20")).encode()
    def reader(bucket, session, version):
        assert (bucket, session, version) == ("private", "2026-10-20", "version-123")
        return raw
    ontime = _session_status(
        now=U(2026,10,21,4), session="2026-10-20", bucket="private",
        head={"LastModified":"2026-10-21T02:46:00Z", "VersionId":"version-123"},
        read_signal=reader)
    assert ontime["status"]=="VERIFIED_RECEIPT_ON_TIME"
    assert ontime["scheduled_execution_proven"] is False
    assert len(ontime["sha256"]) == 64
    late = _session_status(
        now=U(2026,10,21,5), session="2026-10-20", bucket="private",
        head={"LastModified":"2026-10-21T03:55:00+00:00", "VersionId":"version-123"},
        read_signal=reader)
    assert late["status"]=="VERIFIED_RECEIPT_LATE"


def test_absent_version_invalid_frozen_decision_and_missing_vendor_fail():
    import json
    base={"LastModified":"2026-10-21T02:45:00Z", "VersionId":"v1"}
    assert _session_status(now=U(2026,10,21,4),session="2026-10-20",
        bucket="private",head={**base,"VersionId":"null"})["status"]=="INVALID_UNVERSIONED_RECEIPT"
    wrong=_payload("2026-10-20")
    wrong["execution_plan"]["broker_actions_enabled"]=True
    assert _session_status(now=U(2026,10,21,4),session="2026-10-20",
        bucket="private",head=base,
        read_signal=lambda *_:json.dumps(wrong).encode())["status"]=="INVALID_SIGNAL_CONTRACT"
    wrong=_payload("2026-10-20")
    wrong["data_audit"]["source"]="UNVERIFIED_REPLACEMENT"
    assert _session_status(now=U(2026,10,21,4),session="2026-10-20",
        bucket="private",head=base,
        read_signal=lambda *_:json.dumps(wrong).encode())["status"]=="INVALID_SIGNAL_CONTRACT"


def test_snapshot_never_claims_receipt_if_only_infra_working():
    def aws(*args):
        match args[:2]:
            case ("sts", "get-caller-identity"):
                return {"Account":"634740393398"}
            case ("cloudformation", "describe-stacks"):
                return {"Stacks":[{"StackStatus":"UPDATE_COMPLETE","Outputs":[
                    {"OutputKey":"CandidateDataBucket","OutputValue":"private"},
                    *[{"OutputKey":n,"OutputValue":n} for n in (
                        "CandidateSignalOnlyRuleName", "CandidatePaperOnlyRuleName",
                        "CandidateOrchestratorRuleName")]]}]}
            case ("events", "describe-rule"):
                key=args[-1]
                return {"State":"ENABLED" if key=="CandidateSignalOnlyRuleName" else "DISABLED",
                        "ScheduleExpression":{
                            "CandidateSignalOnlyRuleName":"cron(30 2 ? * TUE-SAT *)",
                            "CandidatePaperOnlyRuleName":"cron(20 3 ? * TUE-SAT *)",
                            "CandidateOrchestratorRuleName":"cron(10 0 ? * TUE-SAT *)",
                        }[key]}
            case ("lambda", "get-function-configuration"):
                return {"State":"Active", "LastUpdateStatus":"Successful"}
        pytest.fail(str(args))
    report=snapshot(["2026-10-19","2026-10-20"],now=U(2026,10,21,4),
                    aws=aws,head=lambda _bucket,_session:None)
    assert report["status"]=="INFRA_VERIFIED_RECEIPTS_SEPARATELY_CLASSIFIED"
    assert [x["status"] for x in report["receipts"]]==[
        "MISSING_DUE_RECEIPT","MISSING_DUE_RECEIPT"]
    assert report["paper_automation_verified"] is False
    assert report["broker_orders_authorized"] is False
    assert report["missing_history_not_repaired"] is True
    with pytest.raises(StagingDiagnosticError,match="WRONG_AWS_ACCOUNT"):
        snapshot(["2026-10-20"],now=U(2026,10,21,4),
                 aws=lambda *_:{"Account":"wrong"})


def test_operator_code_does_not_mutate_aws_or_book():
    source=Path("infra/aws/staging_readonly_status.py").read_text()
    for forbidden in (
        "lambda.invoke", "lambda\", \"invoke", "put-object", "delete-object",
        "enable-rule", "disable-rule", "update-function", "cloudformation\", \"deploy",
        "bootstrap=true",
    ):
        assert forbidden not in source

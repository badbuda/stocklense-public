"""No-network adversarial tests for future ST acceptance and zero broker writes."""
from datetime import datetime, timezone, timedelta
import io
import json
import subprocess

import pytest
from infra.aws import stocklens_st_signal_acceptance as a


class STS:
    def __init__(self, account=a.ACCOUNT): self.account=account
    def get_caller_identity(self): return {"Account":self.account}


class CF:
    def describe_stacks(self, StackName):
        name=StackName
        base={"CandidateDataBucket":
                a.BUCKET if name==a.ST else a.PROD_BUCKET,
              "CandidateFunctionName":name+"-candidate",
              "CandidateSessionWatchdogFunctionName":name+"-watchdog"}
        for k in ("CandidateSignalOnlyRuleName","CandidatePaperOnlyRuleName",
                  "CandidateOrchestratorRuleName"):
            base[k]=name+"-"+k
        base["CandidateAlertsTopic"]=f"arn:aws:sns:{a.REGION}:{a.ACCOUNT}:stocklens-st-candidate-alerts"
        return {"Stacks":[{"StackStatus":"CREATE_COMPLETE",
                "Outputs":[{"OutputKey":k,"OutputValue":v} for k,v in base.items()]}]}
    def describe_stack_resource(self, StackName, LogicalResourceId):
        assert StackName==a.ST
        return {"StackResourceDetail":{"PhysicalResourceId":a.ST+"-"+LogicalResourceId}}


class Events:
    def __init__(self, prod_on=False): self.prod_on=prod_on
    def describe_rule(self, Name):
        if Name.endswith("CandidateSignalOnlyRuleName"):
            return {"State":"ENABLED" if Name.startswith(a.ST+"-") else
                    "ENABLED" if self.prod_on else "DISABLED",
                    "ScheduleExpression":a.SIGNAL_CRON}
        if Name.endswith("CandidatePaperOnlyRuleName"):
            return {"State":"DISABLED","ScheduleExpression":"cron(20 3 ? * TUE-SAT *)"}
        if Name.endswith("CandidateOrchestratorRuleName"):
            return {"State":"DISABLED","ScheduleExpression":"cron(10 0 ? * TUE-SAT *)"}
        if Name.endswith("CandidateSessionWatchdogSchedule"):
            return {"State":"ENABLED","ScheduleExpression":"rate(1 hour)"}
        raise AssertionError("UNEXPECTED_RULE:"+Name)
    def list_targets_by_rule(self, Rule):
        kind="watchdog" if "Watchdog" in Rule else "candidate"
        return {"Targets":[{"Arn":"arn:aws:lambda:eu-central-1:634740393398:function:stocklens-st-"+kind}]}


class Lambda:
    def get_function_configuration(self, FunctionName):
        return {"State":"Active","LastUpdateStatus":"Successful",
                "Handler":"infra.aws.independent_pipeline.handler",
                "FunctionArn":f"arn:aws:lambda:eu-central-1:634740393398:function:{FunctionName}",
                "Environment":{"Variables":{"STOCKLENS_DATA_BUCKET":a.BUCKET}}}


class S3:
    def __init__(self, now): self.now=now
    def get_object(self, Bucket, Key):
        assert Bucket==a.BUCKET
        if Key!=a.ACTIVATION:
            raise Missing()
        value=json.dumps({"schema":"STOCKLENS_STAGING_SIGNAL_MONITOR_V1"}).encode()
        return {"VersionId":"version-1","LastModified":
                datetime(2026,10,29,18,0,tzinfo=timezone.utc),
                "ContentLength":len(value),"Body":io.BytesIO(value)}


class Missing(Exception):
    response={"Error":{"Code":"NoSuchKey"}}


class SNS:
    def __init__(self, confirmed=True): self.confirmed=confirmed
    def list_subscriptions_by_topic(self,TopicArn):
        return {"Subscriptions":[{"Protocol":"email",
                "SubscriptionArn":"arn:aws:sns:region:account:sub" if self.confirmed
                else "PendingConfirmation"}]}


class CW:
    def __init__(self, active=False, legacy_namespace=False):
        self.active=active
        self.legacy_namespace=legacy_namespace
    def describe_alarms(self,AlarmNames):
        logical=AlarmNames[0].split("stocklens-st-",1)[-1]
        ns=("AWS/Lambda" if logical in (
             "CandidateSignalErrorsAlarm","CandidateSessionWatchdogErrorsAlarm")
             else "StockLens/IndependentStaging" if self.legacy_namespace
             else "StockLens/IsolatedST")
        return {"MetricAlarms":[{"AlarmName":AlarmNames[0],"ActionsEnabled":True,
                "AlarmActions":[f"arn:aws:sns:{a.REGION}:{a.ACCOUNT}:stocklens-st-candidate-alerts"],
                "Namespace":ns,"Dimensions":[],
                "StateValue":"ALARM" if self.active else "OK"}]}


def services(now, **options):
    return {"sts":STS(options.get("account",a.ACCOUNT)),
            "cloudformation":CF(),
            "events":Events(prod_on=options.get("prod_on",False)),
            "s3":S3(now),
            "sns":SNS(confirmed=options.get("confirmed",True)),
            "cloudwatch":CW(active=options.get("alarm",False),
                             legacy_namespace=options.get("legacy_namespace",False)),
            "lambda":Lambda()}


def test_script_compiles():
    subprocess.run(["python","-m","py_compile","infra/aws/stocklens_st_signal_acceptance.py"],check=True)


def test_future_signal_is_pending_and_no_alarm_is_not_a_trade():
    now=datetime(2026,10,29,19,0,tzinfo=timezone.utc)
    data=a.check(services(now),"2026-10-29",now=now)
    assert data["state"]=="ST_SIGNAL_AWAITING_SCHEDULE"
    assert data["expected_deadline_utc"]=="2026-10-30T03:30:00+00:00"
    assert data["prod_schedules"]=="ALL_DISABLED"
    assert data["st_paper_schedule"]=="DISABLED"
    assert data["watchdog_schedule"]=="ENABLED_HOURLY"
    assert data["alarm_count"]==len(a.ALARM_IDS)
    assert data["broker_orders"] is False and data["aws_mutations"] is False


def test_missing_after_deadline_fails_closed():
    now=datetime(2026,10,30,4,0,tzinfo=timezone.utc)
    d=a.check(services(now),"2026-10-29",now=now)
    assert d["state"]=="ST_SIGNAL_MISSING_AFTER_DEADLINE"
    assert d["signal"] is None


def test_production_cannot_be_active():
    now=datetime(2026,10,29,19,0,tzinfo=timezone.utc)
    with pytest.raises(RuntimeError,match="UNSAFE_EVENTBRIDGE_STATE"):
        a.check(services(now,prod_on=True),"2026-10-29",now=now)


def test_alarm_not_erased_from_report():
    now=datetime(2026,10,29,19,0,tzinfo=timezone.utc)
    d=a.check(services(now,alarm=True),"2026-10-29",now=now)
    assert len(d["alarms_active"])==len(a.ALARM_IDS)


def test_sns_unconfirmed_blocks():
    now=datetime(2026,10,29,19,0,tzinfo=timezone.utc)
    with pytest.raises(RuntimeError,match="ST_SNS_NOT_CONFIRMED"):
        a.check(services(now,confirmed=False),"2026-10-29",now=now)


def test_wrong_account_blocks_first():
    now=datetime(2026,10,29,19,0,tzinfo=timezone.utc)
    with pytest.raises(RuntimeError,match="WRONG_AWS_ACCOUNT"):
        a.check(services(now,account="000000000000"),"2026-10-29",now=now)


def test_s3_denied_is_not_missing():
    class DeniedS3:
        def get_object(self,**kwargs):
            raise PermissionError("denied")
    with pytest.raises(RuntimeError,match="S3_READ_FAILED"):
        a.read_s3(DeniedS3(),a.BUCKET,"signals/2026-10-29.json")


def test_file_contains_no_write_or_broker_calls():
    from pathlib import Path
    c=Path("infra/aws/stocklens_st_signal_acceptance.py").read_text()
    for phrase in (".put_object(", ".put_item(", ".invoke(", ".enable_rule(",
                   ".put_metric_data(", ".start_execution(", ".create_stack("):
        assert phrase not in c


def test_versioned_signal_market_manifest_chain_is_accepted():
    import hashlib
    from datetime import datetime, timezone
    now=datetime(2026,10,30,4,0,tzinfo=timezone.utc)
    class VerifiedS3(S3):
        def get_object(self,Bucket,Key):
            if Key==a.ACTIVATION:
                return super().get_object(Bucket,Key)
            market=b"Date,Close\n2026-10-29,720.1\n"
            sha=hashlib.sha256(market).hexdigest()
            if Key=="market/qqq/2026-10-29.csv":
                body=market;version="ver-market"
            elif Key=="manifests/qqq/2026-10-29.json":
                body=json.dumps({"status":"VERIFIED",
                    "provider":"YFINANCE_QQQ_AUTO_ADJUSTED",
                    "data_type":"QQQ_ADJUSTED_DAILY",
                    "input_key":"market/qqq/2026-10-29.csv",
                    "input_version_id":"ver-market","sha256":sha,
                    "audit":{"csv_sha256":sha,"last_session":"2026-10-29",
                        "source_path":"stocklens.data.load_qqq_history",
                        "data_integrity_status":"FROZEN_YFINANCE_SOURCE_VERIFIED_NOT_INDEPENDENT_VENDOR",
                        "reference_feature_window_sha256":"frozen-feature-sha"}}).encode()
                version="ver-manifest"
            elif Key=="signals/2026-10-29.json":
                body=json.dumps({"mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
                    "latest":{"asof_date":"2026-10-29","level":3,"target_leverage":3},
                    "execution_plan":{"broker_actions_enabled":False},
                    "data_audit":{"source_sha256":sha,
                        "feature_window_sha256":"frozen-feature-sha"},
                    "action":"NO_CHANGE"}).encode()
                version="ver-signal"
            else:
                raise Missing()
            return {"VersionId":version,
                    "LastModified":datetime(2026,10,30,2,35,tzinfo=timezone.utc),
                    "ContentLength":len(body),"Body":io.BytesIO(body)}
    mock=services(now);mock["s3"]=VerifiedS3(now)
    result=a.check(mock,"2026-10-29",now=now)
    assert result["state"]=="ST_SIGNAL_ACCEPTED"
    assert result["signal"]["signal_version_id"]=="ver-signal"
    assert result["signal"]["broker_fills"] is False


def test_shared_custom_metric_namespace_never_accepted_as_st_healthy():
    now=datetime(2026,10,29,19,0,tzinfo=timezone.utc)
    with pytest.raises(RuntimeError,match="ST_WATCHDOG_ALARM_STILL_SHARED"):
        a.check(services(now,legacy_namespace=True),"2026-10-29",now=now)


def signal_fixture(*, signal_time, feature="expected-feature", manifest_feature="expected-feature"):
    """Full-fidelity immutable S3 triple for acceptance regression tests."""
    import hashlib
    from datetime import datetime, timezone
    market=b"Date,Close\n2026-10-29,720.1\n"
    digest=hashlib.sha256(market).hexdigest()
    details={
        "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
        "latest":{"asof_date":"2026-10-29","level":2,"target_leverage":2},
        "execution_plan":{"broker_actions_enabled":False},
        "data_audit":{"source_sha256":digest,"feature_window_sha256":feature}}
    manifest={
        "status":"VERIFIED","provider":"YFINANCE_QQQ_AUTO_ADJUSTED",
        "data_type":"QQQ_ADJUSTED_DAILY",
        "input_key":"market/qqq/2026-10-29.csv",
        "input_version_id":"ver-market","sha256":digest,
        "audit":{
            "csv_sha256":digest,"last_session":"2026-10-29",
            "source_path":"stocklens.data.load_qqq_history",
            "data_integrity_status":"FROZEN_YFINANCE_SOURCE_VERIFIED_NOT_INDEPENDENT_VENDOR",
            "reference_feature_window_sha256":manifest_feature}}
    raw={
        "market/qqq/2026-10-29.csv":market,
        "manifests/qqq/2026-10-29.json":json.dumps(manifest).encode(),
        "signals/2026-10-29.json":json.dumps(details).encode()}
    def stub(s3,bucket,key,**kwargs):
        b=raw[key]
        return {
            "data":b,"sha256":hashlib.sha256(b).hexdigest(),
            "version":"ver-market" if key.startswith("market/") else "version-1",
            "saved_at":signal_time}
    return stub


def test_manual_signal_before_schedule_not_accepted_as_automatic(monkeypatch):
    monkeypatch.setattr(a,"read_s3",signal_fixture(
        signal_time=datetime(2026,10,30,2,25,tzinfo=timezone.utc)))
    with pytest.raises(RuntimeError,match="SIGNAL_ARCHIVED_BEFORE_SCHEDULE"):
        a.validate_signal(None,"2026-10-29",
                          datetime(2026,10,30,4,tzinfo=timezone.utc))


def test_feature_fingerprint_mismatch_blocks_even_if_policy_looks_equal(monkeypatch):
    monkeypatch.setattr(a,"read_s3",signal_fixture(
        signal_time=datetime(2026,10,30,2,35,tzinfo=timezone.utc),
        feature="different",manifest_feature="expected"))
    with pytest.raises(RuntimeError,match="FROZEN_FEATURE_MISMATCH"):
        a.validate_signal(None,"2026-10-29",
                          datetime(2026,10,30,4,tzinfo=timezone.utc))


def test_post_schedule_signal_with_matching_frozen_fingerprint_is_accepted(monkeypatch):
    monkeypatch.setattr(a,"read_s3",signal_fixture(
        signal_time=datetime(2026,10,30,2,35,tzinfo=timezone.utc)))
    verified=a.validate_signal(None,"2026-10-29",
                               datetime(2026,10,30,4,tzinfo=timezone.utc))
    assert verified["status"]=="SHA_VERSION_CHAIN_VERIFIED"
    assert verified["market_sha256"]
    assert verified["broker_fills"] is False

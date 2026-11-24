"""Nov20 fresh ST Epoch5: no backfill, exact preopen source, model only, immutable recovery.

All boto3 calls are replaced by in-memory versioned S3, no AWS credentials.
"""
from datetime import datetime,timezone
import json
from types import SimpleNamespace
import pytest

from infra.aws import sl64_epoch5_preopen as approval
from infra.aws import sl64_epoch5_immutable_store as store
from infra.aws import sl64_epoch5_paper_economic_adapter as adapter
from infra.aws import sl64_epoch5_prospective_runtime as runtime
from infra.aws import sl64_epoch5_watchdog as watchdog
from infra.aws import sl64_epoch5_lambda as handler
from infra.aws import sl64_epoch5_stage_dark_deploy as stage
from infra.aws import sl64_epoch5_automated_release as release
from stocklens.paper import SessionMarket
from test_sl63_epoch4_paper_economic_adapter import FakeS3,signal


class S3(FakeS3):
    def list_object_versions(self, *, Bucket, Prefix, MaxKeys):
        return {"IsTruncated": False, "Versions": [
            {"Key": k} for k in self.items if k.startswith(Prefix)]}

    def get_bucket_versioning(self,**kwargs):
        assert kwargs["Bucket"]==store.ST_BUCKET
        return {"Status":"Enabled"}
    def put_object(self,**kwargs):
        result=super().put_object(**kwargs)
        k=kwargs["Key"]
        raw,version,old,meta=self.items[k]
        self.items[k]=(raw,version,
            datetime(2026,11,20,6,tzinfo=timezone.utc)
            if "preopen-inception-approval.json" in k else
            datetime(2026,11,20,23,40,tzinfo=timezone.utc),meta)
        return result


def setup():
    s3=S3()
    s3.seed("signals/2026-11-19.json",
       signal("2026-11-19","L3"),
       datetime(2026,11,20,5,45,tzinfo=timezone.utc))
    sts=SimpleNamespace(get_caller_identity=lambda:{"Account":store.ST_BUCKET and approval.ACCOUNT})
    a=approval.approve(sts,s3,now="2026-11-20T06:00:00Z",enabled=True)
    assert a["status"]=="EPOCH5_PREOPEN_APPROVAL_STORED_AND_VERSION_VERIFIED"
    return s3,sts,a


def market(day="2026-11-20"):
    return SessionMarket(day,{"QQQ":100.,"TQQQ":50.},
      {"QQQ":100.,"TQQQ":50.},{"QQQ":100.,"TQQQ":50.},
      {"QQQ":0.,"TQQQ":0.},{"QQQ":0.,"TQQQ":0.},
      source="YFINANCE_1M_RAW")


def test_nov20_new_preopen_approval_only_if_source_versioned_and_before_open():
    s3,sts,a=setup()
    assert a["source_key"]=="signals/2026-11-19.json"
    assert a["new_epoch_genesis_or_paper_written"] is False
    assert a["new_approval_written"] is True
    assert len(s3.writes)==1
    again=approval.approve(sts,s3,now="2026-11-20T06:03:00Z",enabled=True)
    assert again["new_approval_written"] is False
    assert len(s3.writes)==1


def test_missing_nov19_frozen_signal_prevents_any_inception():
    s3=S3()
    sts=SimpleNamespace(get_caller_identity=lambda:{"Account":approval.ACCOUNT})
    with pytest.raises(Exception):
        approval.approve(sts,s3,now="2026-11-20T06:00:00Z",enabled=True)
    assert s3.writes==[]


def test_clock_rejects_past_and_future_sessions_and_market_holiday():
    assert runtime.session_from_clock("2026-11-20T23:40:00Z")=="2026-11-20"
    with pytest.raises(adapter.Epoch5IntegrationBlocked):
        runtime.session_from_clock("2026-11-20T18:00:00Z")
    with pytest.raises(runtime.ProspectivePaperBlocked):
        runtime.session_from_clock("2026-11-21T03:00:00Z")
    assert runtime.session_from_clock("2026-11-22T23:40:00Z") is None
    with pytest.raises(store.ImmutableEpoch5Error):
        store.validate_session("2026-11-19")


def test_real_model_nov20_buy_with_no_brkr_then_versioned_watchdog():
    s3,_,a=setup()
    calls=[]
    out=runtime.run_current_session(
      s3,now="2026-11-20T23:40:00Z",
      market_fetch=lambda prior,day:calls.append((prior,day)) or market(day))
    assert calls==[("2026-11-19","2026-11-20")]
    assert out["paper_created_now"] and out["continuity_created_now"]
    assert out["broker_orders"] is False
    assert "BUY" in out["sides"]
    assert out["source"]=="YFINANCE_1M_RAW_SINGLE_VENDOR_NOT_INDEPENDENTLY_ATTESTED"
    assert len(s3.writes)==4 # approval + Genesis + Paper + Continuity
    ok=watchdog.check(s3,"2026-11-20T23:58:00Z")
    assert ok["status"]=="EPOCH5_VERSIONED_RECEIPTS_VERIFIED_SINGLE_VENDOR"
    assert ok["independent_second_vendor_verified"] is False
    assert ok["broker_orders"] is False
    again=runtime.run_current_session(
      s3,now="2026-11-20T23:45:00Z",
      market_fetch=lambda *_: (_ for _ in ()).throw(
         AssertionError("NO_REFETCH_AFTER_PINNED_PAPER")))
    assert again["economic_model_reexecuted"] is False
    assert again["continuity_created_now"] is False
    assert len(s3.writes)==4


def test_real_model_crash_after_paper_then_recover_without_market_reexecution():
    s3,_,_=setup()
    s3.fail_continuity_once=True
    with pytest.raises(store.ImmutableEpoch5Error):
        runtime.run_current_session(
         s3,now="2026-11-20T23:40:00Z",
         market_fetch=lambda prior,day:market(day))
    assert store.key_for("sessions","2026-11-20") in s3.items
    assert store.key_for("continuity","2026-11-20") not in s3.items
    assert len(s3.writes)==3
    out=runtime.run_current_session(
      s3,now="2026-11-20T23:45:00Z",
      market_fetch=lambda *_: (_ for _ in ()).throw(
        AssertionError("MUST_NOT_REGENERATE_BUY")))
    assert out["status"]=="EPOCH5_EXISTING_PAPER_CONTINUITY_VERIFIED_NO_TRADE_REPLAY"
    assert out["new_paper_written"] is False
    assert out["continuity_created_now"] is True
    assert len(s3.writes)==4


def test_dark_lambda_blocks_paper_without_real_aws(monkeypatch):
    monkeypatch.setenv("STOCKLENS_DATA_BUCKET",store.ST_BUCKET)
    monkeypatch.setenv("STOCKLENS_EPOCH5_WRITE_ENABLED","false")
    monkeypatch.setenv("AWS_REGION","eu-central-1")
    import sys
    class FakeBoto:
       def client(self,name,**kw):
          assert name=="s3"
          return S3()
    monkeypatch.setitem(sys.modules,"boto3",FakeBoto())
    with pytest.raises(handler.DarkEpoch5Blocked,
                       match="EPOCH5_WRITE_DISABLED"):
        handler.handler({"mode":handler.PAPER},None)
    with pytest.raises(handler.DarkEpoch5Blocked,
                       match="UNKNOWN_MODE"):
        handler.handler({"mode":"STAGING_PAPER_ONLY"},None)


def test_new_stack_only_has_new_epoch_iam_and_dark_function():
    cfg={"Runtime":"python3.13","Architectures":["x86_64"],
         "MemorySize":1024,"Layers":[]}
    t=stage.template("deployment/epoch5/dark/x.zip",cfg)
    assert {v["Type"] for v in t["Resources"].values()}=={
      "AWS::IAM::Role","AWS::Logs::LogGroup","AWS::Lambda::Function"}
    assert t["Resources"]["DarkLambda"]["Properties"]["Handler"]==(
      "infra.aws.sl64_epoch5_lambda.handler")
    assert t["Resources"]["DarkLambda"]["Properties"][
      "Environment"]["Variables"]["STOCKLENS_EPOCH5_WRITE_ENABLED"]=="false"
    s3p=t["Resources"]["DarkRole"]["Properties"]["Policies"][0][
        "PolicyDocument"]["Statement"]
    puts=next(x for x in s3p if "s3:PutObject" in x["Action"])
    assert all("/paper/epochs/"+store.EPOCH+"/" in x
               for x in puts["Resource"])
    assert all("/paper/sessions/" not in x for x in puts["Resource"])


def test_new_armed_template_event_only_current_session_no_broker():
    cfg={"Runtime":"python3.13","Architectures":["x86_64"],
         "MemorySize":1024,"Layers":[]}
    t=release._new_template("deployment/epoch5/dark/a.zip",cfg,
      "arn:aws:sns:eu-central-1:634740393398:st-alarms",
      armed=True,approval_sha="a"*64)
    p=t["Resources"]["DarkLambda"]["Properties"]
    assert p["Environment"]["Variables"][
      "STOCKLENS_EPOCH5_APPROVAL_SHA256"]=="a"*64
    assert p["Environment"]["Variables"][
      "STOCKLENS_EPOCH5_WRITE_ENABLED"]=="true"
    assert t["Resources"]["PaperRule"]["Properties"]["State"]=="ENABLED"
    assert t["Resources"]["WatchRule"]["Properties"]["State"]=="ENABLED"
    assert '"session"' not in t["Resources"]["PaperRule"]["Properties"][
        "Targets"][0]["Input"]
    policy=t["Resources"]["WatchdogRole"]["Properties"][
        "Policies"][0]["PolicyDocument"]["Statement"]
    assert all("s3:PutObject" not in x["Action"] for x in policy)
    assert t["Outputs"]["BrokerOrdersEnabled"]["Value"]=="false"


def test_retry_on_access_denied_requires_empty_verified_version_inventory():
    error = RuntimeError("denied")
    error.response = {"Error": {"Code": "AccessDenied"}}
    def deny(**kwargs):
        raise error
    s3 = SimpleNamespace(head_object=deny, list_object_versions=lambda **kwargs:
                         {"IsTruncated": False, "Versions": [], "DeleteMarkers": []})
    key = store.key_for("sessions", "2026-11-20")
    assert runtime._read_or_absent(s3, key) is None
    for listing in ({"IsTruncated": True}, {"IsTruncated": False, "DeleteMarkers": [{"Key":key}]},
                    {"IsTruncated": False, "Versions": [{"Key":key}]}):
        s3.list_object_versions = lambda **kwargs: listing
        with pytest.raises(RuntimeError, match="denied"):
            runtime._read_or_absent(s3, key)


def test_fixed_daily_slots_fit_regular_and_early_closes():
    from datetime import timedelta
    for day in ["2026-11-24", "2026-11-27", "2026-07-10", "2025-07-03"]:
        close = adapter.session_times(day)[3]
        assert close + timedelta(minutes=15) <= datetime.fromisoformat(day+"T21:30:00+00:00")
        assert datetime.fromisoformat(day+"T21:59:00+00:00") <= close + timedelta(hours=5)


def test_operator_selects_next_unopened_exchange_session():
    from infra.aws.sl64_epoch5_start import next_open_session
    for now, first in [("2026-11-24T05:00:00", "2026-11-24"),
                       ("2026-11-24T14:30:00", "2026-11-25"),
                       ("2026-11-26T05:00:00", "2026-11-27"),
                       ("2026-11-28T19:00:00", "2026-11-30")]:
        assert next_open_session(datetime.fromisoformat(now).replace(tzinfo=timezone.utc)) == first


def test_future_book_uses_pinned_date_in_runtime_permissions_and_receipts():
    import os
    import subprocess
    import sys
    # New interpreter matches deployment: Lambda and operator both import once.
    script = """
from datetime import datetime, timezone
from test_sl64_epoch5_guarded_release import S3, signal, market, SimpleNamespace
from infra.aws import sl64_epoch5_preopen as approval, sl64_epoch5_immutable_store as store
from infra.aws import sl64_epoch5_prospective_runtime as runtime, sl64_epoch5_watchdog as watchdog
from infra.aws import sl64_epoch5_automated_release as release
from infra.aws import sl64_epoch5_stage_dark_deploy as stage

class ForwardS3(S3):
    def put_object(self, **kwargs):
        result = super().put_object(**kwargs)
        key = kwargs['Key']
        raw, version, _, meta = self.items[key]
        hour = 6 if 'approval' in key else 22
        self.items[key] = raw,version,datetime(2026,11,24,hour,tzinfo=timezone.utc),meta
        return result

s3=ForwardS3()
assert approval.SOURCE == "signals/2026-11-23.json"
s3.seed(approval.SOURCE, signal("2026-11-23","L3"), datetime(2026,11,24,5,tzinfo=timezone.utc))
sts = SimpleNamespace(get_caller_identity=lambda:{"Account":stage.ACCOUNT})
approval.approve(sts,s3,now="2026-11-24T06:00:00Z",enabled=True)
t=release._new_template("deployment/test.zip",{"Runtime":"python3.13"},"topic",armed=True,approval_sha="a"*64)
for fn in ("DarkLambda","WatchdogLambda"):
    assert t["Resources"][fn]["Properties"]["Environment"]["Variables"]["STOCKLENS_ST_FIRST_SESSION"] == store.FIRST
now = datetime(2026,11,24,21,40,tzinfo=timezone.utc)
runtime.run_current_session(s3,now=now,market_fetch=lambda *args:market("2026-11-24"))
assert watchdog.check(s3,now)["session"] == "2026-11-24"
assert all("20261124/" in key for key in s3.writes)
"""
    env = dict(os.environ, STOCKLENS_ST_FIRST_SESSION="2026-11-24", PYTHONPATH=".:tests")
    subprocess.run([sys.executable, "-c", script], env=env, check=True)


@pytest.mark.parametrize("execute,staged", [(False, False), (True, False), (True, True)])
def test_release_from_deployed_dark_stack(monkeypatch, tmp_path, execute, staged):
    import base64
    import hashlib
    from unittest.mock import Mock

    s3, sts, approval_result = setup()
    cfg = {"Runtime": "python3.13"}
    pkg = b"deployed-lambda"
    code_sha = base64.b64encode(hashlib.sha256(pkg).digest()).decode()
    key = "deployment/epoch5/dark/" + hashlib.sha256(pkg).hexdigest() + ".zip"
    topic = "arn:aws:sns:eu-central-1:634740393398:st-topic"
    pin = approval_result["approval_sha256"]
    current = (release._new_template(key, cfg, topic, armed=False, approval_sha=pin)
               if staged else stage.template(key, cfg))
    clients = {name: Mock() for name in ("cloudformation", "events", "lambda", "cloudwatch")}
    clients.update(sts=sts, s3=s3)
    cfn = clients["cloudformation"]
    cfn.describe_stacks.return_value = {"Stacks": [{"StackStatus": "UPDATE_COMPLETE" if staged else "CREATE_COMPLETE"}]}
    cfn.get_template.return_value = {"TemplateBody": current}
    monkeypatch.setattr(release.legacy_approval, "inspect", lambda clients: None)
    monkeypatch.setattr(release, "_package", lambda clients, repo: (pkg, cfg))
    clients["cloudwatch"].describe_alarms.return_value = {"MetricAlarms": [{"AlarmActions": [topic]}]}
    now = datetime(2026, 11, 20, 15, tzinfo=timezone.utc)
    monkeypatch.setattr(release, "datetime", SimpleNamespace(now=lambda tz: now))
    artifact = Mock(return_value=key)
    monkeypatch.setattr(stage, "_artifact", artifact)
    changes = []

    def change_set(clients, body, name, *, stage):
        changes.append(stage)
        cfn.get_template.return_value = {"TemplateBody": body}

    monkeypatch.setattr(release, "_change_set", change_set)

    def configuration(FunctionName):
        name = "DarkLambda" if FunctionName == release.FUNCTION else "WatchdogLambda"
        props = cfn.get_template.return_value["TemplateBody"]["Resources"][name]["Properties"]
        return dict(props, CodeSha256=code_sha, State="Active", LastUpdateStatus="Successful")

    clients["lambda"].get_function_configuration.side_effect = configuration

    def rule(Name):
        name = "PaperRule" if Name == release.PAPER_RULE else "WatchRule"
        return cfn.get_template.return_value["TemplateBody"]["Resources"][name]["Properties"]

    clients["events"].describe_rule.side_effect = rule
    clients["events"].list_targets_by_rule.side_effect = lambda Rule: {"Targets": [
        {"Arn": "arn:aws:lambda:eu-central-1:634740393398:function:" +
         (release.FUNCTION if Rule == release.PAPER_RULE else release.WATCHDOG)}]}
    invoke = Mock(return_value={"historical_session": "2026-11-19", "source": "YFINANCE_1M_RAW",
                                "independent_second_vendor_verified": False, "quote_sha256": "a"*64})
    monkeypatch.setattr(release, "_invoke", invoke)
    result, rc = release.release(clients, tmp_path, execute=execute)
    assert rc == 0 and result["old_dark_zip_sha256_b64"] == code_sha
    assert changes == (([False] if staged else [True, False]) if execute else [])
    assert artifact.call_count == int(execute)
    assert invoke.call_count == (3 if execute else 0)
    assert result["paper_schedules_enabled"] is execute


def test_change_set_retry_uses_new_name_and_reports_provider_reason():
    from unittest.mock import Mock

    cfn = Mock()
    cfn.create_change_set.side_effect = [{"Id": "failed-id"}, {"Id": "retry-id"}]
    waiter_error = RuntimeError("terminal waiter")
    waiter_error.last_response = {"Status": "FAILED", "StatusReason": "Property validation failed"}
    waiter = cfn.get_waiter.return_value
    waiter.wait.side_effect = [waiter_error, None, None]
    cfn.describe_events.return_value = {"OperationEvents": [{
        "LogicalResourceId": "PaperErrorsAlarm", "ValidationStatusReason": "Unknown property Description"}]}
    with pytest.raises(RuntimeError, match="failed-id.*Property validation failed.*PaperErrorsAlarm.*Unknown property"):
        release._change_set({"cloudformation": cfn}, {}, "stage", stage=True)
    cfn.execute_change_set.assert_not_called()
    cfn.describe_change_set.return_value = {"Status": "CREATE_COMPLETE", "Changes": [
        {"ResourceChange": {"Action": "Add", "LogicalResourceId": "PaperRule"}}]}
    release._change_set({"cloudformation": cfn}, {}, "stage", stage=True)
    assert len({c.kwargs["ChangeSetName"] for c in cfn.create_change_set.call_args_list}) == 2
    cfn.execute_change_set.assert_called_once_with(ChangeSetName="retry-id", StackName=release.STACK)

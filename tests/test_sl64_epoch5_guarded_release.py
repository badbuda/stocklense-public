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

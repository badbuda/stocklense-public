"""Exact S3 operator intent is a prerequisite, never Paper recovery."""
from datetime import datetime,timezone
from types import SimpleNamespace
import hashlib
import json
import io
from infra.aws import sl56_epoch4_approval_readback as m


def valid_fake(monkeypatch):
    import infra.aws.sl56_future_paper_inception as p
    consent={
       "schema":"stocklens-epoch4-preopen-inception-intent-v1",
       "book":m.BOOK,"first_session":"2026-11-19",
       "prior_signal_key":"signals/2026-11-18.json",
       "prior_signal_version_id":m.EXPECTED_SIGNAL_VERSION,
       "prior_signal_sha256":m.EXPECTED_SIGNAL_SHA256,
       "starting_cash_usd":100000.0,"starting_shares":{"QQQ":0,"TQQQ":0},
       "old_nav_transferred":False,
       "old_book_last_qualified":p.PRIOR_LAST_QUALIFIED,
       "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
       "broker_orders_authorized":False,
       "genesis_created":False,"paper_trades_created":False}
    now=datetime(2026,11,19,7,0,tzinfo=timezone.utc)
    st={"CandidateDataBucket":p.BUCKET,
        "CandidateFunctionName":"stocklens-st-candidate",
        "CandidatePaperFunctionName":"stocklens-st-paper-candidate"}
    prod={"CandidateDataBucket":p.PROD_BUCKET}
    for prefix,dict_ in (("st-",st),("prod-",prod)):
        for name,postfix in (("CandidateSignalOnlyRuleName","signal"),
                             ("CandidatePaperOnlyRuleName","paper"),
                             ("CandidateOrchestratorRuleName","orch")):
            dict_[name]=prefix+postfix
    def stack(name):return st if name==p.ST else prod
    def old(s3,key):
        if key in p.OLD_PINS:
            return ({"VersionId":"old","LastModified":now},{},p.OLD_PINS[key])
        if key==m.KEY:
            return ({"VersionId":"v-intent","LastModified":now,
                     "Metadata":{"sha256":m.EXPECTED_SHA256}},consent,
                    m.EXPECTED_SHA256)
        if key=="signals/2026-11-18.json":
            return ({"VersionId":m.EXPECTED_SIGNAL_VERSION,
                     "LastModified":datetime(2026,11,19,5,30,tzinfo=timezone.utc)},
                    {"mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
                     "latest":{"asof_date":"2026-11-18"},
                     "execution_plan":{"broker_actions_enabled":False}},
                    m.EXPECTED_SIGNAL_SHA256)
        raise AssertionError("invalid key")
    monkeypatch.setattr(m.p,"immutable_json",old)
    monkeypatch.setattr(m.p,"stack",lambda cf,name:stack(name))
    states={"st-signal":"ENABLED","st-paper":"DISABLED",
            "st-orch":"DISABLED","prod-signal":"DISABLED",
            "prod-paper":"DISABLED","prod-orch":"DISABLED"}
    clients={
      "sts":SimpleNamespace(get_caller_identity=lambda:{"Account":p.ACCOUNT}),
      "cloudformation":SimpleNamespace(),
      "events":SimpleNamespace(describe_rule=lambda Name:{"State":states[Name]}),
      "lambda":SimpleNamespace(get_function_configuration=lambda FunctionName:{
           "State":"Active","LastUpdateStatus":"Successful",
           "CodeSha256":p.PAPER_SHA if FunctionName.endswith("paper-candidate") else p.SIGNAL_SHA,
           "Handler":"infra.aws.independent_paper.handler" if FunctionName.endswith("paper-candidate") else "infra.aws.independent_pipeline.handler",
           "Environment":{"Variables":{"STOCKLENS_DATA_BUCKET":p.BUCKET}}}),
      "s3":SimpleNamespace(
          get_bucket_versioning=lambda Bucket:{"Status":"Enabled"},
          list_object_versions=lambda **kwargs:{
             "IsTruncated":False,"DeleteMarkers":[],
             "Versions":[{"Key":m.KEY,"IsLatest":True,"VersionId":"v-intent"}]})
    }
    return clients,states,consent


def test_exact_signed_s3_approval_only():
    from pytest import MonkeyPatch
    with MonkeyPatch.context() as patch:
        c,_,_=valid_fake(patch)
        out=m.inspect(c)
        assert out["status"]=="APPROVED_PREOPEN_EPOCH4_INTENT_S3_VERIFIED_NOT_PAPER_RECOVERY"
        assert out["new_genesis_checked_or_created"] is False
        assert out["paper_trades_created"] is False
        assert out["aws_mutations"] is False


def test_prod_activation_fails_closed():
    from pytest import MonkeyPatch,raises
    with MonkeyPatch.context() as patch:
        c,states,_=valid_fake(patch)
        states["prod-paper"]="ENABLED"
        with raises(RuntimeError,match="PROD_SCHEDULE_ENABLED"):
            m.inspect(c)


def test_non_unique_approval_history_fails_closed():
    from pytest import MonkeyPatch,raises
    with MonkeyPatch.context() as patch:
        c,_,_=valid_fake(patch)
        c["s3"].list_object_versions=lambda **kwargs:{
            "IsTruncated":False,"Versions":[
                 {"Key":m.KEY,"VersionId":"old","IsLatest":False},
                 {"Key":m.KEY,"VersionId":"v-intent","IsLatest":True}]}
        with raises(RuntimeError,match="APPROVAL_NOT_UNIQUE_LATEST_VERSION"):
            m.inspect(c)


def test_different_operator_approved_cash_fails_closed():
    from pytest import MonkeyPatch,raises
    with MonkeyPatch.context() as patch:
        c,_,payload=valid_fake(patch)
        payload["starting_cash_usd"]=150000.0
        with raises(RuntimeError,match="APPROVAL_RECORD_FIELDS_MISMATCH"):
            m.inspect(c)

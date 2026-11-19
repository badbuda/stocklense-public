"""Future-only ST Paper Epoch4 preopen approval fail-closed tests; NO AWS access."""
from datetime import date,datetime,timezone
import hashlib
import io
import json
from types import SimpleNamespace
import pytest

from infra.aws import sl56_future_paper_inception as m

UTC=timezone.utc
T=datetime(2026,11,19,12,0,tzinfo=UTC)
SAVED=datetime(2026,11,19,6,0,tzinfo=UTC)

class AWSFailure(Exception):
    def __init__(self,code):
        self.response={"Error":{"Code":code}}

class Fake:
    def __init__(self):
        self.account=m.ACCOUNT
        self.rules={"st-signal":"ENABLED","st-paper":"DISABLED","st-orch":"DISABLED",
                    "prod-signal":"DISABLED","prod-paper":"DISABLED","prod-orch":"DISABLED"}
        self.objects={}
        self.puts=[]
        self.lastmod=SAVED
        self.buckets=True
        self.signal={"mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
             "latest":{"asof_date":"2026-11-18"},
             "execution_plan":{"broker_actions_enabled":False}}
        for key,sha in m.OLD_PINS.items():
            # Stub immutable_json for old pins in check(), preserving pin equality.
            self.objects[key]=('v-old',b'{}',SAVED,{})
        self.objects["signals/2026-11-18.json"]=(
            "v-signal",json.dumps(self.signal).encode(),SAVED,{})
    def identity(self):
        return {"Account":self.account}
    def stacks(self, StackName):
        values={"CandidateDataBucket":m.BUCKET if StackName==m.ST else m.PROD_BUCKET}
        for x,n in (("CandidateSignalOnlyRuleName","signal"),
                    ("CandidatePaperOnlyRuleName","paper"),
                    ("CandidateOrchestratorRuleName","orch")):
            values[x]=("st-" if StackName==m.ST else "prod-")+n
        if StackName==m.ST:
            values.update(CandidateFunctionName="stocklens-st-candidate",
                          CandidatePaperFunctionName="stocklens-st-paper-candidate")
        return {"Stacks":[{"StackStatus":"UPDATE_COMPLETE","Outputs":[
            {"OutputKey":k,"OutputValue":v} for k,v in values.items()]}]}
    def rule(self,Name):
        return {"State":self.rules[Name]}
    def config(self,FunctionName):
        paper=FunctionName.endswith("paper-candidate")
        return {"State":"Active","LastUpdateStatus":"Successful",
          "CodeSha256":m.PAPER_SHA if paper else m.SIGNAL_SHA,
          "Handler":("infra.aws.independent_paper.handler" if paper
                     else "infra.aws.independent_pipeline.handler"),
          "Environment":{"Variables":{"STOCKLENS_DATA_BUCKET":m.BUCKET}}}
    def bucket(self, Bucket):
        return {"Status":"Enabled" if self.buckets else "Suspended"}
    def head(self,Bucket,Key):
        if Key not in self.objects:raise AWSFailure("404")
        ver,raw,when,meta=self.objects[Key]
        return {"VersionId":ver,"ContentLength":len(raw),"LastModified":when,
                "Metadata":meta}
    def get(self,Bucket,Key,VersionId):
        ver,raw,_,_=self.objects[Key]
        assert ver==VersionId
        return {"VersionId":ver,"Body":io.BytesIO(raw)}
    def listversions(self,**kw):
        return {"Versions":[{"Key":k,"VersionId":v[0]} for k,v in self.objects.items()
                if k.startswith(kw["Prefix"])], "IsTruncated":False}
    def put(self,Bucket,Key,Body,IfNoneMatch,ContentType,Metadata):
        assert Bucket==m.BUCKET and IfNoneMatch=="*"
        assert ContentType=="application/json" and Key.startswith("paper/epochs/")
        if Key in self.objects:raise AWSFailure("PreconditionFailed")
        self.objects[Key]=("v-new",Body,T,Metadata)
        self.puts.append(Key)
        return {"VersionId":"v-new"}
    def clients(self):
        return {"sts":SimpleNamespace(get_caller_identity=self.identity),
                "cloudformation":SimpleNamespace(describe_stacks=self.stacks),
                "events":SimpleNamespace(describe_rule=self.rule),
                "lambda":SimpleNamespace(get_function_configuration=self.config),
                "s3":SimpleNamespace(get_bucket_versioning=self.bucket,
                                     head_object=self.head,get_object=self.get,
                                     list_object_versions=self.listversions,
                                     put_object=self.put)}

def check(fake, *, now=T):
    # Honest old hash evidence is SHA-pinned in the candidate source. Fake
    # cannot make "{}" match a real SHA, so mock only the old anchor reads.
    original=m.immutable_json
    def oldpin(s3,key):
        if key in m.OLD_PINS:
            return ({"VersionId":"v-old","LastModified":SAVED}, {},m.OLD_PINS[key])
        return original(s3,key)
    m.immutable_json=oldpin
    try:return m.check(fake.clients(),date(2026,11,19),now)
    finally:m.immutable_json=original

def test_readonly_new_session_preflight_and_prior_signal_s3_lag1():
    f=Fake()
    result=check(f)
    assert result["prior_session"]=="2026-11-18"
    assert result["first_session"]=="2026-11-19"
    assert result["opening_utc"]=="2026-11-19T14:30:00+00:00"
    assert result["prior_signal_version_id"]=="v-signal"
    assert f.puts==[]

def test_new_inception_requires_explicit_consent():
    f=Fake();info=check(f)
    with pytest.raises(RuntimeError,match="EXPLICIT_NEW_EPOCH"):
        m.approve(f.clients()["s3"],info,T,explicit=False)
    assert f.puts==[]

def test_conditional_versioned_approval_only_no_paper():
    f=Fake();info=check(f)
    result=m.approve(f.clients()["s3"],info,T,explicit=True)
    assert result["status"]=="ONE_PREOPEN_INTENT_WRITTEN_NOT_PAPER_RECOVERY"
    assert f.puts==[result["approval_key"]]
    assert "approval" in f.puts[0] and "sessions/" not in f.puts[0]
    assert json.loads(f.objects[f.puts[0]][1])["old_nav_transferred"] is False
    with pytest.raises(RuntimeError,match="NEW_EPOCH_PREFIX_ALREADY"):
        m.approve(f.clients()["s3"],info,T,explicit=True)
    assert len(f.puts)==1

@pytest.mark.parametrize("change,code",[
    ("wrong_account","WRONG_ACCOUNT"),
    ("prod_enabled","PRODUCTION_SCHEDULE_ENABLED"),
    ("st_paper_enabled","ST_SCHEDULE_UNEXPECTED"),
    ("versioning_disabled","ST_BUCKET_NOT_VERSIONED"),
    ("late_signal","PREVIOUS_SIGNAL_NOT_SAVED_IN_CORRECT_LAG1_WINDOW"),
    ("wrong_signal","PREVIOUS_DAY_SIGNAL_NOT_FROZEN_SHADOW"),
])
def test_preflight_fails_without_writes(change,code):
    f=Fake()
    if change=="wrong_account":f.account="OTHER"
    if change=="prod_enabled":f.rules["prod-paper"]="ENABLED"
    if change=="st_paper_enabled":f.rules["st-paper"]="ENABLED"
    if change=="versioning_disabled":f.buckets=False
    if change=="late_signal":
        ver,raw,_,meta=f.objects["signals/2026-11-18.json"]
        f.objects["signals/2026-11-18.json"]=(ver,raw,datetime(2026,11,19,16,tzinfo=UTC),meta)
    if change=="wrong_signal":
        f.signal["execution_plan"]["broker_actions_enabled"]=True
        f.objects["signals/2026-11-18.json"]=("v",json.dumps(f.signal).encode(),SAVED,{})
    with pytest.raises(RuntimeError,match=code):check(f)
    assert f.puts==[]

def test_after_exchange_open_no_approval_or_preflight():
    f=Fake()
    late=datetime(2026,11,19,14,31,tzinfo=UTC)
    with pytest.raises(RuntimeError,match="PREOPEN_DEADLINE_PASSED"):check(f,now=late)
    info=check(f)
    with pytest.raises(RuntimeError,match="PREOPEN_DEADLINE_PASSED"):
        m.approve(f.clients()["s3"],info,late,explicit=True)
    assert f.puts==[]

def test_s3_server_timestamp_is_proof_not_operator_clock():
    f=Fake();info=check(f)
    # Already opened at S3 server time, even if caller falsely claims noon.
    f.puts=[]
    original=f.put
    def late_put(**kw):
        result=original(**kw)
        key=f.puts[-1]
        ver,raw,_,meta=f.objects[key]
        f.objects[key]=(ver,raw,datetime(2026,11,19,15,tzinfo=UTC),meta)
        return result
    c=f.clients()["s3"]
    c.put_object=late_put
    with pytest.raises(RuntimeError,match="S3_SERVER_APPROVAL_AFTER_OPEN"):
        m.approve(c,info,T,explicit=True)
    assert len(f.puts)==1  # Ineligible immutable intent stays recorded; NEVER pretend success.

def test_cannot_backdate_nov18_paper():
    with pytest.raises(RuntimeError,match="INELIGIBLE_NEW_EXCHANGE_DAY"):
        m.xcalendar(date(2026,11,18))

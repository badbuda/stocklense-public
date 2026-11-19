"""Strict new-book immutable write mechanics; no real boto3, S3 or Lambda."""
from __future__ import annotations

from copy import deepcopy
from io import BytesIO
from datetime import datetime,timezone
import hashlib
import json
import pytest

from infra.aws import sl63_epoch4_immutable_store as store


class FakeError(Exception):
    def __init__(self,code):
        super().__init__("DELIBERATELY_INJECTED")
        self.response={"Error":{"Code":code}}


class FakeS3:
    def __init__(self):
        self.objects={}
        self.writes=[]
        self.version=0
        self.fail_continuity_once=False
        self.fail_unknown=False
        self.tamper_meta=False
        self.change_head_version=False
        self.change_get_version=False
        self.tamper_body=False
        self.suppress_readback=False
        self.unversioned_put=False
    def put_object(self,**kw):
        assert kw["Bucket"]==store.ST_BUCKET
        assert kw["IfNoneMatch"]=="*"
        if self.fail_unknown:
            raise FakeError("ServiceUnavailable")
        key=kw["Key"]
        if self.fail_continuity_once and "/continuity/" in key:
            self.fail_continuity_once=False
            raise FakeError("500")
        if key in self.objects:
            raise FakeError("PreconditionFailed")
        self.version+=1
        version=f"v-{self.version}"
        self.objects[key]={
            "raw":kw["Body"],"version":version,
            "metadata":dict(kw.get("Metadata") or {})}
        self.writes.append(key)
        return {"VersionId":None if self.unversioned_put else version}
    def head_object(self,**kw):
        assert kw["Bucket"]==store.ST_BUCKET
        k=kw["Key"]
        if self.suppress_readback:
            raise FakeError("NoSuchKey")
        x=self.objects[k]
        metadata=dict(x["metadata"])
        if self.tamper_meta:metadata["sha256"]="0"*64
        return {"ContentLength":len(x["raw"]),
                "VersionId":"wrong" if self.change_head_version else x["version"],
                "Metadata":metadata}
    def get_object(self,**kw):
        assert kw["Bucket"]==store.ST_BUCKET
        x=self.objects[kw["Key"]]
        if kw["VersionId"]!=x["version"]:
            raise FakeError("NoSuchVersion")
        return {"Body":BytesIO(x["raw"]+(b"BAD" if self.tamper_body else b"")),
                "VersionId":"wrong" if self.change_get_version else x["version"]}


def payload(session="2026-11-19"):
    return {"book":store.EPOCH,"session":session,
            "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
            "broker_orders_authorized":False,
            "broker_fills_observed":False,
            "state":{"last_mark_session":session,"shares":{"QQQ":0,"TQQQ":0}}}


def continuation(session, paper):
    return {"book":store.EPOCH,"session":session,
            "status":"MODELLED_RECEIPT_NOT_INDEPENDENTLY_QUALIFIED",
            "broker_orders":False,"broker_fills":False,
            "evidence":{"paper_sha256":paper.sha256,
                        "paper_version_id":paper.version_id,
                        "paper_key":paper.key}}


def test_one_write_and_exact_retry_reuse_verified_version_without_s3_mutation():
    s3=FakeS3()
    key=store.key_for("sessions","2026-11-19")
    a=store.put_once_or_identical(s3,key=key,payload=payload())
    b=store.put_once_or_identical(s3,key=key,payload=payload())
    assert a.created and not b.created
    assert a.sha256==b.sha256 and a.version_id==b.version_id
    assert a.proven_exact_stored_bytes
    assert s3.writes==[key]


def test_crash_after_paper_before_continuity_then_retry_finishes_exactly_once():
    s3=FakeS3()
    s3.fail_continuity_once=True
    with pytest.raises(store.ImmutableEpoch4Error,
                       match="S3_IMMUTABLE_PUT_FAILED_UNCERTAIN_NO_REPLAY"):
        store.save_paper_and_continuity(
            s3,session="2026-11-19",paper_payload=payload(),
            continuation_builder=lambda p:continuation("2026-11-19",p))
    paper=store.key_for("sessions","2026-11-19")
    continuity_key=store.key_for("continuity","2026-11-19")
    assert paper in s3.objects and continuity_key not in s3.objects
    assert len(s3.writes)==1
    report=store.save_paper_and_continuity(
        s3,session="2026-11-19",paper_payload=payload(),
        continuation_builder=lambda p:continuation("2026-11-19",p))
    assert report["status"]=="IMMUTABLE_EPOCH4_PAIR_STORED_VERIFIED_NOT_WATCHDOG_ATTESTED"
    assert report["paper_created_now"] is False
    assert report["continuity_created_now"] is True
    assert report["exact_s3_versions_read_back"]
    assert len(s3.writes)==2
    repeat=store.save_paper_and_continuity(
        s3,session="2026-11-19",paper_payload=payload(),
        continuation_builder=lambda p:continuation("2026-11-19",p))
    assert not repeat["paper_created_now"] and not repeat["continuity_created_now"]
    assert len(s3.writes)==2


def test_changed_paper_after_crash_must_fail_without_continuity():
    s3=FakeS3()
    s3.fail_continuity_once=True
    with pytest.raises(store.ImmutableEpoch4Error):
        store.save_paper_and_continuity(
            s3,session="2026-11-19",paper_payload=payload(),
            continuation_builder=lambda p:continuation("2026-11-19",p))
    forged=payload()
    forged["state"]["shares"]["TQQQ"]=27
    with pytest.raises(store.ImmutableEpoch4Error,
                       match="S3_EXISTING_IMMUTABLE_BYTES_DIFFER"):
        store.save_paper_and_continuity(
            s3,session="2026-11-19",paper_payload=forged,
            continuation_builder=lambda p:continuation("2026-11-19",p))
    assert len(s3.writes)==1


@pytest.mark.parametrize("invalid",[
    "paper/sessions/2026-11-19.json",
    store.PREFIX+"preopen-inception-approval.json",
    store.PREFIX+"continuity/2026-11-18.json",
    "paper/epochs/NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH4_20261119/../fake.json",
    "paper/epochs/NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH4_20261119/head.json",
    "paper/epochs/NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH4_20261119/sessions/2026-11-19.json/evil",
])
def test_only_fresh_immutable_epoch4_paper_continuity_and_genesis_allowed(invalid):
    with pytest.raises(store.ImmutableEpoch4Error):
        store.put_once_or_identical(FakeS3(),key=invalid,payload=payload())


def test_mismatched_existing_receipt_must_never_be_overwritten():
    s3=FakeS3()
    k=store.key_for("sessions","2026-11-19")
    store.put_once_or_identical(s3,key=k,payload=payload())
    old=s3.objects[k]["raw"]
    altered=payload()
    altered["state"]["shares"]["QQQ"]=13
    with pytest.raises(store.ImmutableEpoch4Error,
                       match="S3_EXISTING_IMMUTABLE_BYTES_DIFFER"):
        store.put_once_or_identical(s3,key=k,payload=altered)
    assert s3.objects[k]["raw"]==old
    assert len(s3.writes)==1


@pytest.mark.parametrize("fault",[
    "tamper_meta","change_head_version","change_get_version",
    "tamper_body","suppress_readback","unversioned_put",
])
def test_s3_readback_or_version_discrepancy_never_passes(fault):
    s3=FakeS3()
    setattr(s3,fault,True)
    with pytest.raises((store.ImmutableEpoch4Error,FakeError)):
        store.put_once_or_identical(
            s3,key=store.key_for("sessions","2026-11-19"),
            payload=payload())


def test_broker_or_unqualified_or_wrong_continuity_digest_never_commits():
    s3=FakeS3()
    paper=payload()
    paper["broker_orders_authorized"]=True
    with pytest.raises(store.ImmutableEpoch4Error,
                       match="PAPER_REAL_BROKER_OR_UNATTESTED_MODE_BLOCKED"):
        store.save_paper_and_continuity(
            s3,session="2026-11-19",paper_payload=paper,
            continuation_builder=lambda p:continuation("2026-11-19",p))
    assert s3.writes==[]
    with pytest.raises(store.ImmutableEpoch4Error,
                       match="CONTINUITY_MUST_PIN_EXACT_PAPER_BYTES_AND_VERSION"):
        store.save_paper_and_continuity(
            s3,session="2026-11-19",paper_payload=payload(),
            continuation_builder=lambda p:{
              **continuation("2026-11-19",p),
              "evidence":{**continuation("2026-11-19",p)["evidence"],
                          "paper_sha256":"0"*64}})
    assert s3.writes==[store.key_for("sessions","2026-11-19")]


def test_noncanonical_nonfinite_json_is_rejected_before_any_put():
    with pytest.raises(ValueError):
        store.put_once_or_identical(
            FakeS3(),key=store.key_for("sessions","2026-11-19"),
            payload={"value":float("nan")})


def test_unknown_s3_failure_does_not_become_success():
    s3=FakeS3();s3.fail_unknown=True
    with pytest.raises(store.ImmutableEpoch4Error,
                       match="S3_IMMUTABLE_PUT_FAILED_UNCERTAIN_NO_REPLAY"):
        store.put_once_or_identical(
            s3,key=store.key_for("sessions","2026-11-19"),
            payload=payload())
    assert not s3.writes


def test_no_s3_client_created_inside_module_or_deployed_runtime_changed():
    import inspect
    src=inspect.getsource(store)
    assert "boto3.client" not in src
    assert "lambda.invoke" not in src
    assert "update_function_code" not in src
    assert "put_rule" not in src

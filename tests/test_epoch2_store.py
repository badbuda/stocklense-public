"""Fault-injection tests for Epoch2 S3, no AWS/broker connections."""
from __future__ import annotations

import io
import json
import hashlib

import pytest

from stocklens import paper_epoch as epoch
from stocklens import epoch2_store as m


class S3Error(Exception):
    def __init__(self,code):
        self.response={"Error":{"Code":code}}


class FakeS3:
    def __init__(self):
        self.objects={}
        self.writes=[]
        self.next_version=0
        self.fail_write_key=None
        self.versioning="Enabled"

    def get_bucket_versioning(self, *, Bucket):
        assert Bucket==m.ST_BUCKET
        return {"Status":self.versioning}

    def head_object(self, *, Bucket, Key):
        assert Bucket==m.ST_BUCKET
        if Key not in self.objects:
            raise S3Error("404")
        ver,data=self.objects[Key]
        return {"VersionId":ver,"ContentLength":len(data)}

    def get_object(self, *, Bucket, Key, VersionId):
        assert Bucket==m.ST_BUCKET
        ver,data=self.objects[Key]
        assert ver==VersionId
        return {"VersionId":ver,"Body":io.BytesIO(data)}

    def put_object(self, *, Bucket, Key, Body, ContentType, IfNoneMatch, Metadata):
        assert Bucket==m.ST_BUCKET
        assert ContentType=="application/json"
        assert IfNoneMatch=="*"
        assert Metadata["kind"]=="epoch2"
        assert Metadata["sha256"]==hashlib.sha256(Body).hexdigest()
        assert Key.startswith(m.PREFIX)
        if self.fail_write_key==Key:
            raise S3Error("InternalError")
        if Key in self.objects:
            raise S3Error("PreconditionFailed")
        self.next_version+=1
        ver="verified-st-version-"+str(self.next_version)
        self.objects[Key]=(ver,Body)
        self.writes.append(Key)
        return {"VersionId":ver}


def policy():
    p={
        "status":"FORWARD_ONLY_EPOCH_RECOVERY_PROPOSAL_NOT_DEPLOYABLE",
        "deployment_authorized":False,
        "aws_mutations":False,"broker_orders":False,
        "new_genesis_written":False,"paper_replayed":False,
        "old_book_mutated":False,
        "old_epoch":{
            "book_id":epoch.OLD_BOOK,
            "last_qualified_session":epoch.LAST_OLD_DAY,
            "genesis_and_links":"ALL_MATCH",
            "archived_immutable_anchor_sha256":dict(epoch.HISTORIC_SHA256),
            "state":"BREACHED_AND_PRESERVED_UNCHANGED",
            "historical_alarm_truth":"PRESERVE_HISTORIC_FAIL_CLOSED",
        },
        "unqualified_sessions":[{
            "session":s,
            "proposed_gap_status":"MISSED_UNRECOVERABLE_NO_BACKFILL",
            "old_paper_receipt":"MISSING_AND_MUST_REMAIN_MISSING",
            "old_continuity":"MISSING_AND_MUST_REMAIN_MISSING",
            "broker_execution_claim":False
        } for s in epoch.MISSED],
        "new_epoch":{
            "proposed_book_id":epoch.NEW_BOOK,
            "proposed_first_exchange_session":epoch.FIRST_NEW_DAY,
            "initial_NAV":"NO_VALUE_ASSIGNED_OR_INFERRED",
            "ledger":"DISTINCT_NEW_S3_PREFIX_WITH_OWN_GENESIS_AND_CHAIN",
        }
    }
    return epoch.assess_bootstrap_candidate(
        p,
        verified_prior_signal={
            "session":epoch.PREVIOUS_SIGNAL_DAY,
            "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
            "broker_actions_enabled":False,
            "version_id_present":True,"sha256":"a"*64,
            "archived_at_utc":"2026-11-07T03:25:00Z",
        },
        execution_market={
            "session":epoch.FIRST_NEW_DAY,
            "mode":"CLOSED_REGULAR_XNYS",
            "broker_orders_enabled":False,
            "independent_vendor_close_verified":True,
            "near_session_close_present":True,
            "duplicate_bars_present":False,
            "minute_bars":{"QQQ":389,"TQQQ":388},
        },
        inception={
            "operator_approved":True,
            "approved_at_utc":"2026-11-08T10:00:00Z",
            "source":"NEW_INDEPENDENT_SIMULATED_CAPITAL_NO_OLD_NAV_TRANSFER",
            "old_book_inherited":False,
            "initial_shares":{"QQQ":0,"TQQQ":0},
            "starting_cash_usd":100000,
        },
        now_utc="2026-11-09T22:00:00Z",
    )


def store(*, guard=True, s3=None):
    s3 = s3 if s3 is not None else FakeS3()
    count={"called":0}
    def checked():
        count["called"]+=1
    return m.Epoch2Store(
        s3,verify_before_each_write=checked if guard else None),s3,count


def initialized():
    book,s3,count=store()
    genesis=book.create_genesis(policy())
    book.record_missing_history()
    return book,s3,count,genesis


def paper_candidate(book,day="2026-11-09",previous="2026-11-06",
                    prior_sha=None):
    genesis=book.read(m.GENESIS)
    return {
        "schema":"stocklens-epoch2-session-candidate-v1",
        "book":epoch.NEW_BOOK,
        "session":day,
        "prior_session":previous,
        "status":"MODELED_FORWARD_SESSION_CANDIDATE",
        "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
        "paper_backfill":False,
        "broker_orders_authorized":False,
        "broker_fills_observed":False,
        "genesis_sha256":genesis.sha256,
        "previous_receipt_sha256":prior_sha or genesis.sha256,
        "state":{"last_mark_session":day,"cash":100,"shares":{"QQQ":3,"TQQQ":0}},
        "trades":[{"side":"BUY","symbol":"QQQ","quantity":3}],
    }


def test_default_guard_blocks_all_mutating_operations():
    book,s3,count=store(guard=False)
    with pytest.raises(m.EpochStorageBlocked,match="PRIVATE_WRITE_GUARD_NOT_CONNECTED"):
        book.create_genesis(policy())
    assert s3.writes==[]


def test_st_bucket_only_and_no_legacy_write_keys():
    with pytest.raises(m.EpochStorageBlocked,match="NOT_PINNED_ST_BUCKET"):
        m.Epoch2Store(FakeS3(),bucket="stocklens-prod-private")
    book,s3,_=store()
    with pytest.raises(m.EpochStorageBlocked,match="OUTSIDE_EPOCH2_NAMESPACE"):
        book._create("paper/sessions/2026-11-05.json",{"x":1})
    assert s3.writes==[]


def test_genesis_and_gap_evidence_created_once_and_idempotent():
    book,s3,count=store()
    first=book.create_genesis(policy())
    repeat=book.create_genesis(policy())
    assert first["status"]=="CREATED"
    assert repeat["status"]=="ALREADY_IDENTICAL"
    gap=book.record_missing_history()
    gap_repeat=book.record_missing_history()
    assert gap["status"]=="CREATED"
    assert gap_repeat["status"]=="ALREADY_IDENTICAL"
    assert s3.writes==[m.GENESIS,m.GAPS]
    assert count["called"]==4
    gap_evidence=book.read(m.GAPS).record
    assert gap_evidence["missed_sessions"]==list(epoch.MISSED)
    assert gap_evidence["old_receipt_keys_unchanged"] is True
    assert all(k.startswith(m.PREFIX) for k in s3.objects)


def test_genesis_rejects_modified_old_sha_and_invalid_epoch_contract():
    book,s3,_=store()
    p=policy()
    p["candidate_manifest"]["old_nav_transferred"]=True
    with pytest.raises(m.EpochStorageBlocked,match="INCORRECT_OR_MUTATED"):
        book.create_genesis(p)
    p=policy()
    p["status"]="LIVE_TRADING_APPROVED"
    with pytest.raises(m.EpochStorageBlocked,match="INVALID_OFFLINE_INCEPTION"):
        book.create_genesis(p)
    assert s3.writes==[]


def test_existing_genesis_with_different_bytes_must_not_be_overwritten():
    book,s3,_,_=initialized()
    p=policy()
    p["candidate_manifest"]["starting_cash_usd"]=200000
    p["candidate_manifest_sha256"]=epoch.sha(p["candidate_manifest"])
    with pytest.raises(m.EpochStorageBlocked,match="IMMUTABLE_CONFLICT"):
        book.create_genesis(p)
    assert len(s3.writes)==2


def test_versioning_required_and_get_exact_version():
    book,s3,_=store()
    s3.versioning="Suspended"
    with pytest.raises(m.EpochStorageBlocked,match="VERSIONING_REQUIRED"):
        book.create_genesis(policy())
    s3.versioning="Enabled"
    book.create_genesis(policy())
    read=book.read(m.GENESIS)
    assert read.version=="verified-st-version-1"
    assert read.sha256==hashlib.sha256(read.raw).hexdigest()


def test_first_forward_session_writes_linked_paper_and_continuity():
    book,s3,_,_=initialized()
    result=book.commit_modeled_session(
        paper_candidate(book),
        next_exchange_session=lambda _:"NEVER_CALLED",
        independent_engine_verified=True)
    assert result["status"]=="EPOCH2_STORAGE_LINKED_NOT_ECONOMIC_ACCEPTANCE"
    p=book.read(book.session_key("2026-11-09"))
    c=book.read(book.continuity_key("2026-11-09"))
    assert c.record["paper_sha256"]==p.sha256
    assert c.record["paper_version_id"]==p.version
    assert c.record["previous_record_sha256"]==book.read(m.GENESIS).sha256
    assert result["old_epoch_alarm_preserved"] is True
    assert len(s3.writes)==4
    assert not any(k.startswith("paper/continuity/") or
                   k.startswith("paper/sessions/") for k in s3.writes)


def test_same_first_paper_retry_does_not_duplicate_objects():
    book,s3,_,_=initialized()
    candidate=paper_candidate(book)
    a=book.commit_modeled_session(
        candidate,next_exchange_session=lambda _:"",independent_engine_verified=True)
    b=book.commit_modeled_session(
        candidate,next_exchange_session=lambda _:"",independent_engine_verified=True)
    assert a["continuity_sha256"]==b["continuity_sha256"]
    assert len(s3.writes)==4


def test_crash_between_paper_and_continuity_fails_closed_and_resumes_idempotently():
    book,s3,_,_=initialized()
    key=book.continuity_key("2026-11-09")
    s3.fail_write_key=key
    candidate=paper_candidate(book)
    with pytest.raises(m.EpochStorageBlocked,match="WRITE_FAIL_CLOSED"):
        book.commit_modeled_session(candidate,
            next_exchange_session=lambda _:"",independent_engine_verified=True)
    assert book.read(book.session_key("2026-11-09")) is not None
    assert book.read(key) is None
    assert s3.writes.count(book.session_key("2026-11-09"))==1
    s3.fail_write_key=None
    result=book.commit_modeled_session(candidate,
        next_exchange_session=lambda _:"",independent_engine_verified=True)
    assert result["status"]=="EPOCH2_STORAGE_LINKED_NOT_ECONOMIC_ACCEPTANCE"
    assert s3.writes.count(book.session_key("2026-11-09"))==1


def test_no_pre_genesis_or_no_independent_engine_can_write_paper():
    book,s3,_=store()
    candidate={"book":epoch.NEW_BOOK,"session":"2026-11-09"}
    with pytest.raises(m.EpochStorageBlocked,match="PRIVATE_ENGINE_INDEPENDENT_PROOF_MISSING"):
        book.commit_modeled_session(candidate,
            next_exchange_session=lambda _:None)
    assert s3.writes==[]


def test_second_session_must_have_prior_hash_continuity_and_exchange_day():
    book,s3,_,_=initialized()
    first=paper_candidate(book)
    book.commit_modeled_session(first,next_exchange_session=lambda _:None,
                                independent_engine_verified=True)
    prior=book.read(book.session_key("2026-11-09"))
    second=paper_candidate(book,day="2026-11-10",previous="2026-11-09",
                           prior_sha=prior.sha256)
    with pytest.raises(m.EpochStorageBlocked,match="MARKET_SESSION_CHAIN_GAP"):
        book.commit_modeled_session(second,
            next_exchange_session=lambda _:"2026-11-11",
            independent_engine_verified=True)
    result=book.commit_modeled_session(second,
            next_exchange_session=lambda _:"2026-11-10",
            independent_engine_verified=True)
    assert result["session"]=="2026-11-10"
    c=book.read(book.continuity_key("2026-11-10"))
    previous=book.read(book.continuity_key("2026-11-09"))
    assert c.record["previous_record_sha256"]==previous.sha256


def test_forged_historic_receipt_and_broker_actions_blocked():
    book,s3,_,_=initialized()
    for field,value in (
        ("session","2026-11-05"),
        ("broker_orders_authorized",True),
        ("paper_backfill",True),
        ("mode","LIVE"),
        ("status","RECONSTRUCTED_ACCOUNTING_ONLY"),
    ):
        candidate=paper_candidate(book)
        candidate[field]=value
        with pytest.raises(m.EpochStorageBlocked):
            book.commit_modeled_session(candidate,
                next_exchange_session=lambda _:"",independent_engine_verified=True)
    assert len(s3.writes)==2


def test_wrong_prior_hash_and_unqualified_predecessor_block_write():
    book,s3,_,_=initialized()
    cand=paper_candidate(book)
    cand["previous_receipt_sha256"]="0"*64
    with pytest.raises(m.EpochStorageBlocked,match="MODEL_RECEIPT_STATE_OR_SHA_MISMATCH"):
        book.commit_modeled_session(cand,
            next_exchange_session=lambda _:"",independent_engine_verified=True)
    assert len(s3.writes)==2


def test_invalid_403_head_never_looks_missing():
    class Denied(FakeS3):
        def head_object(self, *,Bucket,Key):
            raise S3Error("AccessDenied")
    book,_,_=store(s3=Denied())
    with pytest.raises(m.EpochStorageBlocked,match="HEAD_FAIL_CLOSED"):
        book.create_genesis(policy())


def test_json_nan_or_corrupted_receipt_cannot_be_committed():
    with pytest.raises(ValueError):
        m.encode({"cash":float("nan")})
    book,s3,_=store()
    s3.objects[m.GENESIS]=("v1",b"not-json")
    with pytest.raises(m.EpochStorageBlocked,match="PINNED_READ_FAIL_CLOSED"):
        book.read(m.GENESIS)


def test_only_epoch2_keys_and_no_auto_aws_or_broker_connection():
    from pathlib import Path
    source=Path("stocklens/epoch2_store.py").read_text()
    assert "import boto3" not in source
    assert ".invoke(" not in source
    assert ".set_alarm_state(" not in source
    assert "execute_change_set(" not in source
    assert ".enable_rule(" not in source
    assert ".disable_rule(" not in source


def test_delete_marker_cannot_be_treated_as_empty_receipt_key():
    class DeletedKey(FakeS3):
        def head_object(self, *, Bucket, Key):
            exc = S3Error("404")
            exc.response["ResponseMetadata"] = {
                "HTTPHeaders": {"x-amz-delete-marker": "true"}
            }
            raise exc

    book, s3, _ = store(s3=DeletedKey())
    with pytest.raises(m.EpochStorageBlocked, match="IMMUTABLE_KEY_DELETE_MARKER"):
        book.create_genesis(policy())
    assert s3.writes == []


@pytest.mark.parametrize("raw", [
    b'{ "book": "fake" }',
    b'{"book":"old","book":"forged"}',
    b'{"cash":NaN}',
])
def test_noncanonical_receipts_fail_closed_without_writes(raw):
    book, s3, _ = store()
    s3.objects[m.GENESIS] = ("verified-version", raw)
    with pytest.raises(m.EpochStorageBlocked, match="NON_CANONICAL_RECEIPT"):
        book.read(m.GENESIS)
    assert s3.writes == []


def test_receipt_sha_metadata_mismatch_fails_closed():
    class WrongMetadata(FakeS3):
        def head_object(self, *, Bucket, Key):
            meta = super().head_object(Bucket=Bucket, Key=Key)
            meta["Metadata"] = {"sha256": "0" * 64}
            return meta

    s3 = WrongMetadata()
    s3.objects[m.GENESIS] = ("verified-version", m.encode({"book": epoch.NEW_BOOK}))
    book, _, _ = store(s3=s3)
    with pytest.raises(m.EpochStorageBlocked, match="RECEIPT_METADATA_SHA_MISMATCH"):
        book.read(m.GENESIS)
    assert s3.writes == []

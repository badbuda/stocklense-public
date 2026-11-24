"""New epoch from Nov20 only, real ST signal must be preopen and versioned."""
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json
from types import SimpleNamespace
import pytest
from infra.aws import sl64_epoch5_preopen as m
from infra.aws import sl64_epoch5_immutable_store as store
from test_sl63_epoch4_paper_economic_adapter import (
    FakeS3,signal)


class ST(FakeS3):
    def get_bucket_versioning(self,**kwargs):
        assert kwargs["Bucket"]==store.ST_BUCKET
        return {"Status":"Enabled"}
    def put_object(self,**kwargs):
        result=super().put_object(**kwargs)
        key=kwargs["Key"]
        raw,version,_,meta=self.items[key]
        self.items[key]=(raw,version,
          datetime(2026,11,20,6,tzinfo=timezone.utc),meta)
        return result


def setup():
    s3=ST()
    key=m.SOURCE
    doc=signal("2026-11-19","L3")
    s3.seed(key,doc,datetime(2026,11,20,5,45,tzinfo=timezone.utc))
    sts=SimpleNamespace(get_caller_identity=lambda:{"Account":m.ACCOUNT})
    return sts,s3


def test_no_mutation_without_explicit_approval():
    sts,s3=setup()
    result=m.approve(sts,s3,now="2026-11-20T06:00:00Z",enabled=False)
    assert result["status"]=="EPOCH5_APPROVAL_PREFLIGHT_READONLY"
    assert result["aws_mutations"] is False
    assert s3.writes==[]


def test_new_forward_only_preopen_approval_is_versioned_and_idempotent():
    sts,s3=setup()
    result=m.approve(sts,s3,now="2026-11-20T06:00:00Z",enabled=True)
    assert result["status"]=="EPOCH5_PREOPEN_APPROVAL_STORED_AND_VERSION_VERIFIED"
    assert result["approval_key"]==store.PREFIX+"preopen-inception-approval.json"
    assert result["new_epoch_genesis_or_paper_written"] is False
    assert result["broker_orders"] is False
    assert result["approval_version_id"]
    assert len(s3.writes)==1
    repeat=m.approve(sts,s3,now="2026-11-20T06:01:00Z",enabled=True)
    assert repeat["new_approval_written"] is False
    assert len(s3.writes)==1


def test_reject_source_after_open_and_absent_signal_without_writes():
    sts,s3=setup()
    info=s3.items[m.SOURCE]
    s3.items[m.SOURCE]=(info[0],info[1],
       datetime(2026,11,20,15,tzinfo=timezone.utc),info[3])
    with pytest.raises(m.PreopenNotEligible,
                       match="PRIOR_SIGNAL_NOT_FROZEN"):
        m.approve(sts,s3,now="2026-11-20T06:00:00Z",enabled=True)
    assert s3.writes==[]


def test_reject_new_approval_when_preopen_window_elapsed():
    sts,s3=setup()
    with pytest.raises(m.PreopenNotEligible,
                       match="EPOCH5_PREOPEN_WINDOW_CLOSED"):
        m.approve(sts,s3,now="2026-11-20T15:00:00Z",enabled=True)
    assert s3.writes==[]


def test_wrong_account_no_approval():
    sts,s3=setup()
    bad=SimpleNamespace(get_caller_identity=lambda:{"Account":"000000000000"})
    with pytest.raises(m.PreopenNotEligible,match="WRONG_AWS_ACCOUNT"):
        m.approve(bad,s3,now="2026-11-20T06:00:00Z",enabled=True)
    assert s3.writes==[]

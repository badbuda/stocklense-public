"""Dark ST Lambda entrypoint tests: no real AWS, never place broker orders."""
import os
from types import SimpleNamespace
from unittest.mock import Mock
import pytest

from infra.aws import sl63_epoch4_lambda as app
from infra.aws import sl63_epoch4_immutable_store as store


@pytest.fixture
def dark(monkeypatch):
    monkeypatch.setenv("STOCKLENS_DATA_BUCKET",app.ST)
    monkeypatch.setenv("STOCKLENS_EPOCH4_WRITE_ENABLED","false")
    monkeypatch.setenv("AWS_REGION",app.REGION)
    class FakeBoto:
        def client(self,name,**kw):
            assert name=="s3"
            return Mock()
    import sys
    monkeypatch.setitem(sys.modules,"boto3",FakeBoto())
    return True


def test_dark_cannot_execute_new_paper(dark):
    with pytest.raises(app.DarkEpoch4Blocked,match="EPOCH4_WRITE_DISABLED"):
        app.handler({"mode":app.PAPER,"session":"2026-11-19"},None)


def test_unknown_mode_fail_closed(dark):
    with pytest.raises(app.DarkEpoch4Blocked,match="UNKNOWN_MODE"):
        app.handler({"mode":"STAGING_PAPER_ONLY"},None)


def test_wrong_bucket_rejected_before_boto3(dark,monkeypatch):
    monkeypatch.setenv("STOCKLENS_DATA_BUCKET","prod-bucket")
    with pytest.raises(app.DarkEpoch4Blocked,match="NOT_EXPECTED_ST_BUCKET"):
        app.handler({"mode":app.READINESS},None)


def test_readiness_only_with_deny_write_flag(dark,monkeypatch):
    monkeypatch.setenv("STOCKLENS_EPOCH4_WRITE_ENABLED","true")
    with pytest.raises(app.DarkEpoch4Blocked,match="READINESS_MUST_REMAIN_DARK"):
        app.handler({"mode":app.READINESS},None)


def test_readiness_uses_only_approval_and_prior_frozen_signal(dark,monkeypatch):
    seen=[]
    approval={"sha256":"a"*64}
    sig={"sha256":"b"*64}
    monkeypatch.setattr(app.adapter,"_approval",
                        lambda s3,d,opening:seen.append("APPROVAL") or approval)
    monkeypatch.setattr(app.adapter,"_source_signal",
                        lambda s3,d,prior,close,opening,a:
                        seen.append("SIGNAL") or sig)
    response=app.handler({"mode":app.READINESS},None)
    assert response["status"]=="EPOCH4_DARK_LAMBDA_READINESS_S3_READ_ONLY"
    assert response["new_epoch_paper_or_continuity_written"] is False
    assert response["schedule_enabled"] is False
    assert response["broker_orders"] is False
    assert seen==["APPROVAL","SIGNAL"]


def test_no_broker_import_or_lambda_unsafe_settings():
    import inspect
    s=inspect.getsource(app)
    assert "broker" not in [line.strip() for line in s.splitlines()
                            if line.strip().startswith("import ")]
    assert "update_function_code" not in s
    assert "put_rule" not in s
    assert app.FIRST=="2026-11-19"
    assert store.EPOCH=="NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH4_20261119"

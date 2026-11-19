"""S3 versioned receipt watchdog: fails closed on incomplete chain."""
from datetime import datetime,timezone
import json
import pytest
from infra.aws import sl63_epoch4_watchdog as w
from infra.aws import sl63_epoch4_prospective_runtime as p
from infra.aws import sl63_epoch4_immutable_store as store
from test_sl63_epoch4_prospective_runtime import market
from test_sl63_epoch4_paper_economic_adapter import FakeS3,setup_approval


def built():
    s3=FakeS3();setup_approval(s3)
    p.run_current_session(s3,now="2026-11-19T23:40:00Z",
                          market_fetch=lambda _,day:market(day))
    return s3


def test_watchdog_verified_after_completed_only():
    s3=built()
    report=w.check(s3,"2026-11-19T23:58:00Z")
    assert report["status"]=="EPOCH4_VERSIONED_RECEIPTS_VERIFIED_SINGLE_VENDOR"
    assert report["broker_orders"] is False
    assert report["independent_second_vendor_verified"] is False


def test_watchdog_missing_receipt_fails_without_fabrication():
    s3=built()
    del s3.items[store.key_for("continuity","2026-11-19")]
    before=len(s3.writes)
    with pytest.raises(Exception):
        w.check(s3,"2026-11-19T23:58:00Z")
    assert len(s3.writes)==before


def test_watchdog_wrong_paper_sha_detected():
    s3=built()
    key=store.key_for("continuity","2026-11-19")
    old=s3.items[key]
    val=json.loads(old[0]);val["evidence"]["paper_sha256"]="0"*64
    s3.seed(key,val,old[2])
    with pytest.raises(p.ProspectivePaperBlocked,
                       match="WATCHDOG_CONTINUITY_PAPER_VERSION_HASH_MISMATCH"):
        w.check(s3,"2026-11-19T23:58:00Z")


def test_market_holiday_is_no_write_skip():
    s3=FakeS3()
    report=w.check(s3,"2026-11-22T23:58:00Z")
    assert report["status"]=="XNYS_CLOSED_WATCHDOG_NO_CHECK"
    assert s3.writes==[]

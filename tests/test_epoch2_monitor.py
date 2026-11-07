"""Pure epoch2 read-only monitor does not declare operational success."""
from __future__ import annotations

from copy import deepcopy
import pytest

from stocklens import paper_epoch as epoch
from stocklens import epoch2_store as storage
from stocklens import epoch2_monitor as monitor


class StoreStub:
    def __init__(self):
        self.data={}
    def add(self,key,record,version="s3v1"):
        raw=storage.encode(record)
        r=storage.Receipt(key,version,storage.digest(raw),raw,record)
        self.data[key]=r
        return r
    def __call__(self,key):
        return self.data.get(key)


def complete():
    reader=StoreStub()
    manifest={"book":epoch.NEW_BOOK,"old_book":epoch.OLD_BOOK,
              "original_book_anchors":dict(epoch.HISTORIC_SHA256)}
    g=reader.add(storage.GENESIS,{
        "book":epoch.NEW_BOOK,"old_book_preserved":True,
        "broker_orders":False,"manifest":manifest,
        "manifest_sha256":epoch.sha(manifest)})
    reader.add(storage.GAPS,{
        "book":epoch.NEW_BOOK,"status":"MISSED_UNRECOVERABLE_NO_BACKFILL",
        "old_receipt_keys_unchanged":True,
        "missed_sessions":list(epoch.MISSED),
        "new_genesis_sha256":g.sha256,
        "original_anchor_sha256":dict(epoch.HISTORIC_SHA256)})
    prior_paper=g.sha256
    prior_cont=g.sha256
    prior_day=epoch.PREVIOUS_SIGNAL_DAY
    for d in ("2026-11-09","2026-11-10"):
        pkey=storage.Epoch2Store.session_key(d)
        p=reader.add(pkey,{
            "book":epoch.NEW_BOOK,"session":d,
            "prior_session":prior_day,
            "previous_receipt_sha256":prior_paper,
            "genesis_sha256":g.sha256,
            "broker_orders_authorized":False,
            "broker_fills_observed":False,
            "paper_backfill":False,
            "status":"MODELED_FORWARD_SESSION_CANDIDATE",
            "state":{"last_mark_session":d},
        },version="paper-"+d)
        c=reader.add(storage.Epoch2Store.continuity_key(d),{
            "book":epoch.NEW_BOOK,"session":d,
            "status":"STRUCTURAL_ONLY_NOT_ECONOMICALLY_QUALIFIED",
            "paper_key":p.key,
            "paper_sha256":p.sha256,
            "paper_version_id":p.version,
            "previous_record_sha256":prior_cont,
            "genesis_sha256":g.sha256,
            "broker_orders":False,"broker_fills":False,
            "old_epoch_alarm_preserved":True,
        },version="cont-"+d)
        prior_paper=p.sha256
        prior_cont=c.sha256
        prior_day=d
    return reader


def test_no_genesis_always_fails_closed():
    result=monitor.inspect_epoch2(lambda _:None,
        expected_completed_sessions=["2026-11-09"])
    assert result["new_epoch"]=="MISSING_GENESIS_FAIL_CLOSED"
    assert result["old_epoch"]=="FAIL_CLOSED_MISSING_2026_11_05_AND_06"
    assert result["operational_watchdog_green"] is False


def test_gap_audit_required_even_when_genesis_present():
    r=complete()
    del r.data[storage.GAPS]
    x=monitor.inspect_epoch2(r,expected_completed_sessions=["2026-11-09"])
    assert x["new_epoch"]=="MISSING_HISTORIC_GAP_AUDIT_FAIL_CLOSED"


def test_original_alarm_never_cleared_even_when_two_structural_sessions_linked():
    r=complete()
    out=monitor.inspect_epoch2(r,expected_completed_sessions=["2026-11-09","2026-11-10"])
    assert out["new_epoch"]=="STRUCTURALLY_LINKED_NOT_LIVE_ACCOUNTING_ACCEPTANCE"
    assert out["structurally_verified_prior_sessions"]==2
    assert out["operational_watchdog_green"] is False
    assert out["original_alarms_may_be_cleared"] is False
    assert out["cross_epoch_nav_allowed"] is False
    assert out["calendar_is_provided_not_independently_attested"] is True


def test_missing_continuity_after_paper_is_not_qualified():
    r=complete()
    del r.data[storage.Epoch2Store.continuity_key("2026-11-10")]
    out=monitor.inspect_epoch2(r,expected_completed_sessions=["2026-11-09","2026-11-10"])
    assert out["new_epoch"]=="SESSION_MISSING_OR_HALF_COMMITTED_FAIL_CLOSED"
    assert out["first_missing_session"]=="2026-11-10"
    assert out["structurally_verified_prior_sessions"]==1


def test_missing_entire_session_never_accepted():
    r=complete()
    out=monitor.inspect_epoch2(r,expected_completed_sessions=[
        "2026-11-09","2026-11-10","2026-11-11"])
    assert out["first_missing_session"]=="2026-11-11"
    assert out["operational_watchdog_green"] is False


@pytest.mark.parametrize("kind,field,value",[
    ("continuity","paper_sha256","0"*64),
    ("continuity","paper_version_id","wrong"),
    ("continuity","previous_record_sha256","0"*64),
    ("continuity","status","RECONSTRUCTED_ACCOUNTING_ONLY"),
    ("continuity","broker_orders",True),
    ("continuity","old_epoch_alarm_preserved",False),
    ("paper","previous_receipt_sha256","0"*64),
    ("paper","broker_orders_authorized",True),
    ("paper","paper_backfill",True),
    ("paper","status","LATE_REPLAY"),
])
def test_tampering_any_critical_link_fails_closed(kind,field,value):
    r=complete()
    key=(storage.Epoch2Store.session_key("2026-11-10") if kind=="paper"
         else storage.Epoch2Store.continuity_key("2026-11-10"))
    prev=r.data[key]
    record={**prev.record,field:value}
    r.add(key,record,version=prev.version)
    with pytest.raises(storage.EpochStorageBlocked):
        monitor.inspect_epoch2(r,expected_completed_sessions=["2026-11-09","2026-11-10"])


def test_wrong_genesis_archive_anchor_blocks():
    r=complete()
    old=r.data[storage.GENESIS]
    record=deepcopy(old.record)
    record["manifest"]["original_book_anchors"]["paper/sessions/2026-11-04.json"]="0"*64
    record["manifest_sha256"]=epoch.sha(record["manifest"])
    r.add(storage.GENESIS,record)
    with pytest.raises(storage.EpochStorageBlocked,match="INVALID_NEW_EPOCH_GENESIS"):
        monitor.inspect_epoch2(r,expected_completed_sessions=["2026-11-09"])


@pytest.mark.parametrize("dates",[
    [],["2026-11-10"],["2026-11-09","2026-11-09"],
    ["2026-11-10","2026-11-09"],
])
def test_invalid_or_incomplete_supplied_calendar_blocked(dates):
    with pytest.raises(storage.EpochStorageBlocked,match="INVALID_EXPECTED_SESSION_CALENDAR"):
        monitor.inspect_epoch2(complete(),expected_completed_sessions=dates)


def test_monitor_has_no_aws_clients_or_active_alarm_operations():
    from pathlib import Path
    source=Path("stocklens/epoch2_monitor.py").read_text()
    for x in ("import boto3",".put_object(", ".invoke(",
              ".set_alarm_state(", ".put_metric_data(", "GenUI."):
        assert x not in source

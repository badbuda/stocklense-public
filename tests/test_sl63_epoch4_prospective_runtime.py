"""Prospective Epoch4: forced full-session vendor provenance, safe crash-retry.
No real AWS/network; versioned S3 and injected market functions only.
"""
from datetime import datetime, timezone
import pytest

from infra.aws import sl63_epoch4_prospective_runtime as p
from infra.aws import sl63_epoch4_paper_economic_adapter as adapter
from infra.aws import sl63_epoch4_immutable_store as store
from stocklens.paper import SessionMarket
from test_sl63_epoch4_paper_economic_adapter import FakeS3,setup_approval,signal


def market(day="2026-11-19",source="YFINANCE_1M_RAW"):
    return SessionMarket(day,
        {"QQQ":100.,"TQQQ":50.},
        {"QQQ":100.,"TQQQ":50.},
        {"QQQ":100.,"TQQQ":50.},
        {"QQQ":0.,"TQQQ":0.},
        {"QQQ":0.,"TQQQ":0.},
        source=source)


def test_single_vendor_is_not_falsely_independently_qualified():
    evidence=p._quote_payload(market())
    assert evidence["single_vendor"]=="YFINANCE_1M_RAW"
    assert evidence["independent_second_vendor_verified"] is False
    assert evidence["broker_fill_verified"] is False
    assert evidence["synthetic_quotes"] is False
    assert len(evidence["quotes_and_actions_sha256"])==64
    with pytest.raises(p.ProspectivePaperBlocked,
                       match="EPOCH4_NOT_REAL_YFINANCE"):
        p._quote_payload(market(source="SYNTHETIC_NOT_REAL_VENDOR"))


def test_ill_timed_future_historical_and_exchange_holiday_never_backfill():
    with pytest.raises(adapter.Epoch4IntegrationBlocked,
                       match="UNCOMPLETED_MARKET_SESSION"):
        p.session_from_clock("2026-11-19T17:00:00Z")
    with pytest.raises(p.ProspectivePaperBlocked,
                       match="EPOCH4_PROSPECTIVE_WINDOW_EXPIRED_NO_BACKFILL"):
        p.session_from_clock("2026-11-20T03:00:00Z")
    assert p.session_from_clock("2026-11-19T23:40:00Z")=="2026-11-19"
    assert p.session_from_clock("2026-11-22T23:40:00Z") is None


def test_direct_first_session_buy_then_idempotent_market_free_retry():
    s3=FakeS3(); setup_approval(s3)
    calls=[]
    def fetch(prior,session):
        calls.append((prior,session))
        return market(session)
    r=p.run_current_session(s3,now="2026-11-19T23:40:00Z",
                            market_fetch=fetch)
    assert r["paper_created_now"] and r["continuity_created_now"]
    assert r["broker_orders"] is False
    assert r["source"]=="YFINANCE_1M_RAW_SINGLE_VENDOR_NOT_INDEPENDENTLY_ATTESTED"
    assert calls==[("2026-11-18","2026-11-19")]
    assert len(s3.writes)==3
    r2=p.run_current_session(s3,now="2026-11-19T23:42:00Z",
                             market_fetch=lambda *_: (_ for _ in ()).throw(
                                 AssertionError("MUST_NOT_FETCH_MARKET_ON_RETRY")))
    assert r2["status"]=="EPOCH4_EXISTING_PAPER_CONTINUITY_VERIFIED_NO_TRADE_REPLAY"
    assert r2["economic_model_reexecuted"] is False
    assert r2["continuity_created_now"] is False
    assert len(s3.writes)==3


def test_continuity_put_failure_then_recover_without_refetching_vendor():
    s3=FakeS3();setup_approval(s3)
    s3.fail_continuity_once=True
    with pytest.raises(store.ImmutableEpoch4Error):
        p.run_current_session(s3,now="2026-11-19T23:40:00Z",
                              market_fetch=lambda a,b:market(b))
    assert store.key_for("sessions","2026-11-19") in s3.items
    assert store.key_for("continuity","2026-11-19") not in s3.items
    before=len(s3.writes)
    report=p.run_current_session(s3,now="2026-11-19T23:48:00Z",
                                 market_fetch=lambda *_: (_ for _ in ()).throw(
                                     AssertionError("NO_RECOMPUTATION")))
    assert report["continuity_created_now"] is True
    assert report["new_paper_written"] is False
    assert report["economic_model_reexecuted"] is False
    assert len(s3.writes)==before+1
    assert len(s3.writes)==3


def test_missing_previous_day_refuses_market_fetch_and_paper_write():
    s3=FakeS3();setup_approval(s3)
    s3.seed("signals/2026-11-19.json",signal("2026-11-19","CASH"),
            datetime(2026,11,19,23,tzinfo=timezone.utc))
    calls=[]
    with pytest.raises(Exception):
        p.run_current_session(s3,now="2026-11-20T23:40:00Z",
            market_fetch=lambda *args:calls.append(args) or market("2026-11-20"))
    assert calls==[]
    assert s3.writes==[]


def test_tampered_paper_signal_hash_blocks_recovery_without_writes():
    s3=FakeS3();setup_approval(s3)
    p.run_current_session(s3,now="2026-11-19T23:40:00Z",
                          market_fetch=lambda x,y:market(y))
    old=s3.items[store.key_for("sessions","2026-11-19")]
    payload=__import__("json").loads(old[0])
    payload["signal"]["sha256"]="0"*64
    s3.seed(store.key_for("sessions","2026-11-19"),payload,old[2])
    before=len(s3.writes)
    with pytest.raises(p.ProspectivePaperBlocked,
                       match="EXISTING_PAPER_SIGNAL_SOURCE_DRIFT"):
        p.run_current_session(s3,now="2026-11-19T23:44:00Z",
                              market_fetch=lambda *_:None)
    assert len(s3.writes)==before

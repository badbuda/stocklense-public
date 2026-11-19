"""Actual StockLens economic functions to Epoch4 immutable fake S3 (NO AWS)."""
from __future__ import annotations

from datetime import datetime,timezone
from io import BytesIO
from copy import deepcopy
import hashlib
import json

import pytest
import exchange_calendars as xcals

from infra.aws import sl63_epoch4_paper_economic_adapter as adapter
from infra.aws import sl63_epoch4_immutable_store as store
from stocklens.core import LEVEL_LEVERAGE, TARGET_INVESTED_FRACTION, weights_for_leverage
from stocklens.paper import SessionMarket


class FakeError(Exception):
    def __init__(self,code):
        super().__init__("INJECTED_FAKE_S3")
        self.response={"Error":{"Code":code}}


class FakeS3:
    def __init__(self):
        self.items={}
        self.writes=[]
        self.n=0
        self.fail_continuity_once=False
    def seed(self,key,payload,when):
        data=json.dumps(payload,sort_keys=True,separators=(",",":")).encode()
        self.n+=1
        self.items[key]=(data,"v-"+str(self.n),when,{"sha256":hashlib.sha256(data).hexdigest()})
    def head_object(self,*,Bucket,Key):
        assert Bucket==store.ST_BUCKET
        if Key not in self.items:raise FakeError("NoSuchKey")
        data,version,when,meta=self.items[Key]
        return {"ContentLength":len(data),"VersionId":version,
                "LastModified":when,"Metadata":dict(meta)}
    def get_object(self,*,Bucket,Key,VersionId):
        assert Bucket==store.ST_BUCKET
        if Key not in self.items or self.items[Key][1]!=VersionId:
            raise FakeError("NoSuchVersion")
        data,version,_,_=self.items[Key]
        return {"Body":BytesIO(data),"VersionId":version}
    def put_object(self,*,Bucket,Key,Body,IfNoneMatch,Metadata,**kw):
        assert Bucket==store.ST_BUCKET and IfNoneMatch=="*"
        if self.fail_continuity_once and "/continuity/" in Key:
            self.fail_continuity_once=False
            raise FakeError("500")
        if Key in self.items:
            raise FakeError("PreconditionFailed")
        self.n+=1
        version="v-"+str(self.n)
        self.items[Key]=(Body,version,datetime(2026,11,25,0,tzinfo=timezone.utc),
                         dict(Metadata))
        self.writes.append(Key)
        return {"VersionId":version}


def signal(day,regime):
    lev=0 if regime=="CASH" else LEVEL_LEVERAGE[int(regime[1])]
    q,t=weights_for_leverage(lev)
    return {
        "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
        "action":"EXPOSURE_CHANGE",
        "generated_at_utc":day+"T22:30:00Z",
        "execution_plan":{"broker_actions_enabled":False},
        "latest":{"asof_date":day,
                  "level":1 if regime=="CASH" else int(regime[1]),
                  "defense_active":regime=="CASH",
                  "target_leverage":float(lev),
                  "qqq_weight":q*TARGET_INVESTED_FRACTION,
                  "tqqq_weight":t*TARGET_INVESTED_FRACTION}
    }


def fake_market(day):
    return SessionMarket(day,
                         {"QQQ":100.,"TQQQ":50.},
                         {"QQQ":100.,"TQQQ":50.},
                         {"QQQ":100.,"TQQQ":50.},
                         {"QQQ":0.,"TQQQ":0.},
                         {"QQQ":0.,"TQQQ":0.},
                         source="SYNTHETIC_NOT_REAL_VENDOR")


def setup_approval(s3):
    first="2026-11-19"
    cal=xcals.get_calendar("XNYS")
    prev=cal.previous_session(first).date().isoformat()
    s3.seed("signals/"+prev+".json",signal(prev,"L3"),
            datetime(2026,11,19,5,30,tzinfo=timezone.utc))
    saved=s3.items["signals/"+prev+".json"]
    approval={
        "schema":"stocklens-epoch4-preopen-inception-intent-v1",
        "book":store.EPOCH,"first_session":first,
        "prior_signal_key":"signals/"+prev+".json",
        "prior_signal_version_id":saved[1],
        "prior_signal_sha256":hashlib.sha256(saved[0]).hexdigest(),
        "starting_cash_usd":100000.0,
        "starting_shares":{"QQQ":0,"TQQQ":0},
        "old_nav_transferred":False,
        "broker_orders_authorized":False,
        "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
    }
    s3.seed(store.PREFIX+"preopen-inception-approval.json",
            approval,datetime(2026,11,19,6,14,tzinfo=timezone.utc))


def run_day(s3,day):
    return adapter.build_and_store_pair(
        s3,session=day,market=fake_market(day),
        observed_at_utc=day+"T23:30:00Z")


def test_epoch4_buy_sell_buy_then_no_change_and_exact_retries():
    s3=FakeS3()
    setup_approval(s3)
    days=["2026-11-19","2026-11-20","2026-11-23","2026-11-24"]
    regimes=["L3","CASH","L2","L2"]
    sides=[]
    for day,target in zip(days,regimes):
        prev=xcals.get_calendar("XNYS").previous_session(day).date().isoformat()
        if day!="2026-11-19":
            s3.seed("signals/"+prev+".json",signal(prev,target),
                    datetime.fromisoformat(prev+"T23:00:00+00:00"))
        result=run_day(s3,day)
        assert result["status"]=="EPOCH4_MODELED_PAIR_WRITTEN_NOT_LIVE_ACCEPTANCE"
        assert result["paper_created_now"] and result["continuity_created_now"]
        assert result["all_injected_quotes_not_independently_verified"]
        assert result["broker_orders"] is False
        sides.extend(result["sides"])
        count=len(s3.writes)
        repeat=run_day(s3,day)
        assert not repeat["paper_created_now"]
        assert not repeat["continuity_created_now"]
        assert len(s3.writes)==count
    assert {"BUY","SELL"}.issubset(set(sides))
    assert len(s3.writes)==1+2*len(days)
    assert not any(k.startswith("paper/sessions/") for k in s3.writes)


def test_continuity_crash_then_recovered_without_duplicate_paper():
    s3=FakeS3()
    setup_approval(s3)
    s3.fail_continuity_once=True
    with pytest.raises(store.ImmutableEpoch4Error):
        run_day(s3,"2026-11-19")
    assert store.key_for("sessions","2026-11-19") in s3.items
    assert store.key_for("continuity","2026-11-19") not in s3.items
    assert len(s3.writes)==2  # Genesis plus modeled Paper
    result=run_day(s3,"2026-11-19")
    assert result["paper_created_now"] is False
    assert result["continuity_created_now"] is True
    assert len(s3.writes)==3
    again=run_day(s3,"2026-11-19")
    assert not again["paper_created_now"] and not again["continuity_created_now"]
    assert len(s3.writes)==3


def test_late_signal_or_wrong_approval_must_not_write_paper():
    s3=FakeS3()
    setup_approval(s3)
    sig=s3.items["signals/2026-11-18.json"]
    s3.items["signals/2026-11-18.json"]=(sig[0],sig[1],
        datetime(2026,11,19,17,0,tzinfo=timezone.utc),sig[3])
    with pytest.raises(adapter.Epoch4IntegrationBlocked,
                       match="LAG1_SIGNAL_NOT_FROZEN_BEFORE_OPEN"):
        run_day(s3,"2026-11-19")
    assert not s3.writes


def test_uncompleted_market_session_or_illegal_historic_replay_rejected():
    s3=FakeS3()
    setup_approval(s3)
    with pytest.raises(adapter.Epoch4IntegrationBlocked,
                       match="UNCOMPLETED_MARKET_SESSION"):
        adapter.build_and_store_pair(
            s3,session="2026-11-19",market=fake_market("2026-11-19"),
            observed_at_utc="2026-11-19T14:00:00Z")
    with pytest.raises(store.ImmutableEpoch4Error,
                       match="NO_HISTORICAL_EPOCH4_BACKFILL"):
        adapter.build_and_store_pair(
            s3,session="2026-11-18",market=fake_market("2026-11-18"),
            observed_at_utc="2026-11-19T23:00:00Z")
    assert not s3.writes


def test_missing_previous_continuity_refuses_next_session():
    s3=FakeS3()
    setup_approval(s3)
    s3.fail_continuity_once=True
    with pytest.raises(store.ImmutableEpoch4Error):
        run_day(s3,"2026-11-19")
    s3.seed("signals/2026-11-19.json",signal("2026-11-19","CASH"),
            datetime(2026,11,19,23,tzinfo=timezone.utc))
    with pytest.raises(FakeError) as exc:
        run_day(s3,"2026-11-20")
    assert exc.value.response["Error"]["Code"]=="NoSuchKey"
    assert store.key_for("sessions","2026-11-20") not in s3.items


def test_prior_continuity_tampering_blocks_next_economic_orders():
    s3=FakeS3()
    setup_approval(s3)
    run_day(s3,"2026-11-19")
    s3.seed("signals/2026-11-19.json",signal("2026-11-19","CASH"),
            datetime(2026,11,19,23,tzinfo=timezone.utc))
    key=store.key_for("continuity","2026-11-19")
    orig=s3.items[key]
    raw=json.loads(orig[0])
    raw["evidence"]["paper_sha256"]="0"*64
    s3.seed(key,raw,orig[2])
    with pytest.raises(adapter.Epoch4IntegrationBlocked,
                       match="PRIOR_CONTINUITY_MISSING_OR_NOT_PINNED"):
        run_day(s3,"2026-11-20")
    assert store.key_for("sessions","2026-11-20") not in s3.items


def test_wrong_vendor_session_or_disarmed_broker():
    s3=FakeS3()
    setup_approval(s3)
    with pytest.raises(adapter.Epoch4IntegrationBlocked,
                       match="MARKET_SESSION_MISMATCH"):
        adapter.build_and_store_pair(
            s3,session="2026-11-19",market=fake_market("2026-11-20"),
            observed_at_utc="2026-11-19T23:30:00Z")
    assert not s3.writes

"""SL9-024 standalone fail-closed prospective StockLens 8.0 evidence journal.

A local hash chain is NOT an external immutable receipt. This library
enforces offline session schemas; production capture, WORM/third-party proof,
PIT vendor and brokerage NBBO/fills are separately required.
"""
from __future__ import annotations
import hashlib
import json
import re
from datetime import date, datetime, timezone
from pathlib import Path
import exchange_calendars as xcals

ZERO="0"*64
HEX=re.compile(r"^[0-9a-f]{64}$")
MODES=("COMPLETE","MISSED")
SCHEMA=1

def canon(obj):
    return json.dumps(obj,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def digest(obj):
    return hashlib.sha256(canon(obj)).hexdigest()

def utc(value):
    try:
        t=datetime.fromisoformat(value.replace("Z","+00:00"))
    except (ValueError,AttributeError) as exc:
        raise ValueError("FORWARD_INVALID_UTC_RECEIPT") from exc
    if t.tzinfo is None or t.utcoffset()!=timezone.utc.utcoffset(t):
        raise ValueError("FORWARD_RECEIPT_NOT_UTC")
    return t.astimezone(timezone.utc)

def hexdigest(value,field):
    if not isinstance(value,str) or not HEX.fullmatch(value):
        raise ValueError("FORWARD_INVALID_DIGEST_"+field)

def validate(record,previous=None):
    if not isinstance(record,dict) or record.get("schema_version")!=SCHEMA:
        raise ValueError("FORWARD_BAD_SCHEMA")
    if record.get("model")!="STOCKLENS_8_0_FROZEN" or record.get("broker_orders_authorized") is not False:
        raise ValueError("FORWARD_MODEL_OR_BROKER_UNSAFE")
    day=record.get("session_date")
    try:
        d=date.fromisoformat(day)
        if d.isoformat()!=day or not xcals.get_calendar("XNYS").is_session(day):
            raise ValueError()
    except (TypeError,ValueError,OverflowError) as exc:
        raise ValueError("FORWARD_NOT_XNYS_SESSION") from exc
    status=record.get("status")
    if status not in MODES:raise ValueError("FORWARD_UNREGISTERED_STATUS")
    parent=record.get("previous_record_sha256")
    hexdigest(parent,"PARENT")
    if previous is None:
        if parent!=ZERO:raise ValueError("FORWARD_FIRST_PARENT_NOT_ZERO")
    else:
        if previous.get("record_sha256")!=parent:raise ValueError("FORWARD_BROKEN_CHAIN")
        if previous["session_date"]>=day:raise ValueError("FORWARD_NOT_MONOTONE")
        cal=xcals.get_calendar("XNYS")
        if cal.next_session(previous["session_date"]).date().isoformat()!=day:
            raise ValueError("FORWARD_GAP_WITHOUT_MISSED_RECORD")
    receipt=record.get("external_server_receipt")
    if status=="MISSED":
        if not isinstance(record.get("missing_reason"),str) or not record["missing_reason"].strip():
            raise ValueError("FORWARD_MISSED_WITHOUT_REASON")
        if receipt is not None or record.get("market_source") is not None:
            raise ValueError("FORWARD_MISSED_MUST_NOT_BACKFILL")
    else:
        if not isinstance(receipt,dict) or not isinstance(record.get("market_source"),dict):
            raise ValueError("FORWARD_MISSING_SOURCE_RECEIPT")
        if receipt.get("verified_external_append_only") is not True:
            raise ValueError("FORWARD_NOT_INDEPENDENTLY_TIMESTAMPED")
        if receipt.get("server") not in ("EXTERNAL_WORM_STORE","RFC3161_VALIDATED"):
            raise ValueError("FORWARD_UNACCEPTED_EXTERNAL_RECEIPT")
        if not isinstance(receipt.get("signed_proof_id"),str) or not receipt["signed_proof_id"].strip():
            raise ValueError("FORWARD_MISSING_SIGNED_RECEIPT")
        server_time=utc(receipt.get("received_at_utc"))
        if server_time.date()<d:raise ValueError("FORWARD_RECEIPT_PRE_SESSION")
        src=record["market_source"]
        if src.get("qqq_kind")!="OBSERVED_REAL_ETF" or src.get("tqqq_kind")!="OBSERVED_REAL_ETF":
            raise ValueError("FORWARD_SYNTHETIC_PRICE_REJECTED")
        for key in ("qqq_raw_sha256","tqqq_raw_sha256"):
            hexdigest(src.get(key),key)
        sig=record.get("signal")
        if not isinstance(sig,dict) or sig.get("core_sha256") is None:
            raise ValueError("FORWARD_MISSING_FROZEN_SIGNAL")
        hexdigest(sig.get("core_sha256"),"CORE")
        hexdigest(sig.get("prior_input_sha256"),"INPUT")
        hexdigest(sig.get("signal_sha256"),"SIGNAL")
        if utc(sig.get("external_preopen_received_utc"))>=datetime.fromisoformat(day+"T09:30:00-04:00").astimezone(timezone.utc):
            # Do not hardcode DST from this illustrative cutoff: further check below.
            pass
        import zoneinfo
        market_open=datetime.combine(d,datetime.min.time().replace(hour=9,minute=30),tzinfo=zoneinfo.ZoneInfo("America/New_York")).astimezone(timezone.utc)
        if utc(sig["external_preopen_received_utc"])>=market_open:
            raise ValueError("FORWARD_SIGNAL_RECEIVED_AFTER_OPEN")
        if sig.get("signal_asof_date")>=day:
            raise ValueError("FORWARD_FUTURE_SIGNAL")
    payload={k:v for k,v in record.items() if k!="record_sha256"}
    hexdigest(record.get("record_sha256"),"RECORD")
    if digest(payload)!=record["record_sha256"]:
        raise ValueError("FORWARD_HASH_TAMPERING")
    return True

def build_record(payload,previous=None):
    r=dict(payload)
    r["previous_record_sha256"]=ZERO if previous is None else previous["record_sha256"]
    r["record_sha256"]=digest(r)
    validate(r,previous)
    return r

def verify(rows):
    if not isinstance(rows,list):raise ValueError("FORWARD_JOURNAL_NOT_LIST")
    old=None
    for row in rows:
        validate(row,old)
        old=row
    return {"status":"SCHEMA_CHAIN_CHECK_PASSED_NOT_EXTERNAL_RECEIPT_ATTESTATION",
            "records":len(rows),"complete":sum(x["status"]=="COMPLETE" for x in rows),
            "missed":sum(x["status"]=="MISSED" for x in rows),
            "independent_external_verification_performed":False,
            "broker_fills_proven":False,"alpha_proven":False,
            "capital_authorized":False}

def read(path):
    p=Path(path)
    return verify([json.loads(l) for l in p.read_text().splitlines()]) if p.is_file() else verify([])

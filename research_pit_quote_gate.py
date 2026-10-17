"""Offline open-window NBBO *shape* gate, not a proof of executable fills."""
from __future__ import annotations
from datetime import datetime,time,timezone
from hashlib import sha256
from zoneinfo import ZoneInfo
import math,re
from research_pit_json_integrity import strict_json
import exchange_calendars as xcals

NY=ZoneInfo("America/New_York")
HEX=re.compile("^[0-9a-f]{64}$")
SYMBOLS={"QQQ","QLD","TQQQ"}

def utc(v):
    if not isinstance(v,str):raise ValueError("missing quote time")
    try:d=datetime.fromisoformat(v.replace("Z","+00:00"))
    except ValueError as e:raise ValueError("invalid quote time") from e
    if d.tzinfo is None or d.utcoffset() is None:raise ValueError("naive quote time")
    return d.astimezone(timezone.utc)

def audit(raw):
    if not isinstance(raw,bytes) or not raw or len(raw)>8*1024*1024:
        raise ValueError("invalid quote file")
    records=strict_json(raw)
    if not isinstance(records,list):raise ValueError("quotes must be list")
    seen=set();sessions=set()
    cal=xcals.get_calendar("XNYS")
    for x in records:
        if not isinstance(x,dict) or x.get("symbol") not in SYMBOLS:
            raise ValueError("unsupported quote symbol")
        if x.get("source_type")!="NBBO" or x.get("quote_condition")!="REGULAR":
            raise ValueError("not a regular NBBO candidate")
        h=x.get("source_record_sha256")
        if not isinstance(h,str) or not HEX.fullmatch(h):
            raise ValueError("invalid quote hash")
        stamp=utc(x.get("timestamp_utc"))
        local=stamp.astimezone(NY);day=local.date().isoformat()
        if not cal.is_session(day):raise ValueError("not an XNYS session")
        if not time(9,30)<=local.time()<time(9,33):
            raise ValueError("not opening 09:30-09:33 ET")
        key=(x["symbol"],stamp)
        if key in seen:raise ValueError("duplicate quote time")
        seen.add(key)
        bid=x.get("bid");ask=x.get("ask")
        if any(type(v) not in (int,float) or not math.isfinite(v) or v<=0
               for v in (bid,ask)):
            raise ValueError("invalid bid or ask")
        if bid>ask:raise ValueError("crossed quote")
        if any(type(x.get(k)) is not int or x[k]<=0 for k in ("bid_size","ask_size")):
            raise ValueError("invalid quote sizes")
        sessions.add(day)
    return {
        "kind":"OPEN_WINDOW_NBBO_FEASIBILITY",
        "status":"BLOCKED_NO_INDEPENDENT_SIP_FEED_OR_BROKER_FILLS",
        "raw_sha256":sha256(raw).hexdigest(),
        "syntactically_valid_quote_rows":len(records),
        "session_labels":len(sessions),
        "independently_qualified_nbbo_rows":0,
        "sip_feed_proven":False,"quote_entitlement_verified":False,
        "broker_fills_observed":False,"h3_alpha_established":False,
        "synthetic_tqqq":False,"frozen_stocklens8_changed":False,
        "broker_orders_authorized":False,"capital_authorized":False,
    }

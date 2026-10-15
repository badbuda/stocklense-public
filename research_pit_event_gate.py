"""Offline SEC/GDELT/scheduled-event metadata audit; no historical first-seen claims."""
from __future__ import annotations
from datetime import datetime,timezone
from hashlib import sha256
import json,re

HEX=re.compile("^[0-9a-f]{64}$")
SOURCES={"SEC_EDGAR","GDELT_2_0_GKG","FOMC_SCHEDULE","BLS_CPI_SCHEDULE"}

def utc(value):
    if not isinstance(value,str):raise ValueError("missing timestamp")
    try:d=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError as e:raise ValueError("invalid timestamp") from e
    if d.tzinfo is None or d.utcoffset() is None:raise ValueError("naive timestamp")
    return d.astimezone(timezone.utc)

def audit(raw):
    if not isinstance(raw,bytes) or not raw or len(raw)>8*1024*1024:
        raise ValueError("invalid file size")
    records=json.loads(raw.decode("utf-8"))
    if not isinstance(records,list):raise ValueError("events must be list")
    seen=set();counts={k:0 for k in sorted(SOURCES)}
    for x in records:
        if not isinstance(x,dict) or x.get("provider") not in SOURCES:
            raise ValueError("unregistered event provider")
        provider=x["provider"];identity=x.get("source_record_id")
        if not isinstance(identity,str) or not identity or len(identity)>256:
            raise ValueError("invalid record ID")
        key=(provider,identity)
        if key in seen:raise ValueError("duplicate event ID")
        seen.add(key)
        h=x.get("source_record_sha256")
        if not isinstance(h,str) or not HEX.fullmatch(h):
            raise ValueError("invalid source hash")
        published=utc(x.get("published_at_utc"))
        collected=utc(x.get("collected_at_utc"))
        if collected<published:raise ValueError("collection precedes publication")
        if provider=="SEC_EDGAR":
            accepted=utc(x.get("accepted_at_utc"))
            if accepted>collected:raise ValueError("SEC accepted after collection")
        if provider in {"FOMC_SCHEDULE","BLS_CPI_SCHEDULE"}:
            utc(x.get("scheduled_release_at_utc"))
            if any(x.get(field) is not None for field in
                   ("actual_value","expected_value","result","surprise")):
                raise ValueError("scheduled calendar leaked outcome")
        counts[provider]+=1
    return {
        "kind":"EVENT_FIRST_SEEN_FEASIBILITY",
        "status":"BLOCKED_NO_INDEPENDENT_HISTORICAL_RECEIPT",
        "raw_sha256":sha256(raw).hexdigest(),
        "metadata_rows":len(records),"provider_counts":counts,
        "qualified_tradable_event_rows":0,
        "sec_acceptance_equals_public_dissemination":False,
        "gdelt_batch_equals_article_first_seen":False,
        "historical_consensus_verified":False,
        "provider_first_seen_independently_verified":False,
        "synthetic_tqqq":False,"frozen_stocklens8_changed":False,
        "capital_authorized":False,"broker_orders_authorized":False,
    }

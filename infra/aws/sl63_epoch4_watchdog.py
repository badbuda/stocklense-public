"""Independent ST Epoch4 receipt monitor, read-only S3, no broker."""
from __future__ import annotations
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
import os
from infra.aws import sl63_epoch4_prospective_runtime as p
from infra.aws import sl63_epoch4_paper_economic_adapter as a
from infra.aws import sl63_epoch4_immutable_store as store

REGION="eu-central-1"
WATCH_MODE="STAGING_EPOCH4_CONTINUITY_WATCHDOG"
ST=store.ST_BUCKET


def check(s3,now):
    session=p.session_from_clock(now)
    if session is None:
        return {"status":"XNYS_CLOSED_WATCHDOG_NO_CHECK","broker_orders":False}
    g=a._verified(s3,store.key_for("genesis"))
    paper=a._verified(s3,store.key_for("sessions",session))
    continuity=a._verified(s3,store.key_for("continuity",session))
    pp,cp=paper["payload"],continuity["payload"]
    p.require(g["payload"].get("book")==store.EPOCH and
              pp.get("book")==store.EPOCH and
              pp.get("session")==session and
              pp.get("broker_orders_authorized") is False and
              pp.get("broker_fills_observed") is False and
              pp.get("state",{}).get("last_mark_session")==session,
              "WATCHDOG_GENESIS_OR_PAPER_NOT_ATTESTED")
    ev=cp.get("evidence") or {}
    p.require(cp.get("book")==store.EPOCH and
              cp.get("session")==session and
              cp.get("broker_orders") is False and
              cp.get("broker_fills") is False and
              ev.get("paper_sha256")==paper["sha256"] and
              ev.get("paper_version_id")==paper["version_id"] and
              ev.get("paper_key")==paper["key"],
              "WATCHDOG_CONTINUITY_PAPER_VERSION_HASH_MISMATCH")
    source=pp.get("market_evidence") or {}
    p.require(source.get("schema")==p.SOURCE_SCHEMA and
              source.get("single_vendor")==p.VENDOR and
              source.get("synthetic_quotes") is False and
              source.get("independent_second_vendor_verified") is False,
              "WATCHDOG_MARKET_SOURCE_NOT_REVIEWABLE")
    return {"status":"EPOCH4_VERSIONED_RECEIPTS_VERIFIED_SINGLE_VENDOR",
            "session":session,
            "paper_version_id":paper["version_id"],
            "paper_sha256":paper["sha256"],
            "continuity_version_id":continuity["version_id"],
            "continuity_sha256":continuity["sha256"],
            "broker_orders":False,
            "independent_second_vendor_verified":False}


def handler(event,context):
    if not isinstance(event,dict) or event.get("mode")!=WATCH_MODE:
        raise RuntimeError("WATCHDOG_UNKNOWN_MODE")
    if os.getenv("STOCKLENS_DATA_BUCKET")!=ST:
        raise RuntimeError("WATCHDOG_NOT_ST_BUCKET")
    import boto3
    s3=boto3.client("s3",region_name=REGION)
    return check(s3,datetime.now(timezone.utc))

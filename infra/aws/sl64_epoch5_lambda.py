"""Isolated ST Epoch5 Lambda: live prospective modeled Paper only if armed.

Readiness dark mode remains no-write. Scheduled Paper never accepts event
dates or externally provided quotes: derive NYSE session from real UTC clock,
verify original preopen approval, strict Yahoo 1m bars, immutable S3 record
and prior continuity. Broker orders always disabled.
"""
from __future__ import annotations
from datetime import datetime, timezone
import os
from infra.aws import sl64_epoch5_paper_economic_adapter as adapter
from infra.aws import sl64_epoch5_prospective_runtime as prospective
from infra.aws import sl64_epoch5_immutable_store as store

REGION="eu-central-1"
FIRST="2026-11-20"
READINESS="STAGING_EPOCH5_DARK_READINESS"
PREFLIGHT="STAGING_EPOCH5_READ_ONLY_PREFLIGHT"
VENDOR_PREFLIGHT="STAGING_EPOCH5_VENDOR_CONNECTIVITY_READONLY"
PAPER="STAGING_EPOCH5_MODELED_PAPER"
ST="stocklens-st-candidatedata-6jj7i9fxjmfr"


class DarkEpoch5Blocked(RuntimeError):
    pass


def _require(ok,reason):
    if not ok:raise DarkEpoch5Blocked(reason)


def handler(event,context):
    _require(type(event) is dict,"EVENT_OBJECT_REQUIRED")
    _require(os.getenv("STOCKLENS_DATA_BUCKET")==ST,
             "NOT_EXPECTED_ST_BUCKET")
    _require(os.getenv("AWS_REGION",REGION)==REGION,
             "REGION_DIFFERENT_FROM_ST_PIN")
    mode=event.get("mode")
    _require(mode in (READINESS,PREFLIGHT,VENDOR_PREFLIGHT,PAPER),
             "UNKNOWN_MODE_FAIL_CLOSED")
    import boto3
    s3=boto3.client("s3",region_name=REGION)
    if mode in (READINESS,PREFLIGHT,VENDOR_PREFLIGHT):
        if mode==READINESS:
            _require(os.getenv("STOCKLENS_EPOCH5_WRITE_ENABLED")=="false",
                     "READINESS_MUST_REMAIN_DARK")
        else:
            _require(os.getenv("STOCKLENS_EPOCH5_WRITE_ENABLED") in (
                "false","true"),"UNCONFIGURED_EPOCH5_WRITE_GATE")
        _,priorclose,opening,_=adapter._market_clock(
            FIRST,"2026-11-20T23:00:00Z")
        approval=adapter._approval(s3,FIRST,opening)
        prior,close,_,_=adapter._market_clock(
            FIRST,"2026-11-20T23:00:00Z")
        signal=adapter._source_signal(
            s3,FIRST,prior,close,opening,approval)
        if os.getenv("STOCKLENS_EPOCH5_WRITE_ENABLED")=="true":
            _require(os.getenv("STOCKLENS_EPOCH5_APPROVAL_SHA256")==
                     approval["sha256"],"EPOCH5_APPROVAL_SHA_DRIFT")
        if mode==VENDOR_PREFLIGHT:
            # Read-only Nov19 completed 1-minute vendor connectivity proof
            # before approved first session Nov20; no modeled Paper write.
            from stocklens import paper as model
            quote=model.fetch_execution_market("2026-11-18","2026-11-19")
            quality=prospective._quote_payload(quote)
            _require(quote.session_date=="2026-11-19",
                     "VENDOR_PREFLIGHT_HISTORIC_SESSION_MISMATCH")
            return {
                "status":"EPOCH5_HISTORIC_YFINANCE_1M_READ_ONLY_PREFLIGHT",
                "historical_session":"2026-11-19",
                "source":quality["single_vendor"],
                "quote_sha256":quality["quotes_and_actions_sha256"],
                "independent_second_vendor_verified":False,
                "broker_orders":False,
                "new_epoch_paper_or_continuity_written":False,
            }
        return {
            "status":("EPOCH5_DARK_LAMBDA_READINESS_S3_READ_ONLY"
                      if mode==READINESS else
                      "EPOCH5_ARMED_READINESS_S3_READ_ONLY"),
            "epoch":store.EPOCH,
            "approval_sha256":approval["sha256"],
            "approved_prior_signal_sha256":signal["sha256"],
            "new_epoch_paper_or_continuity_written":False,
            "schedule_enabled":False,
            "broker_orders":False,
            "independently_qualified":False,
        }
    _require(os.getenv("STOCKLENS_EPOCH5_WRITE_ENABLED")=="true",
             "EPOCH5_WRITE_DISABLED_DARK_DEPLOYMENT")
    _require(isinstance(os.getenv("STOCKLENS_EPOCH5_APPROVAL_SHA256"),str)
             and len(os.getenv("STOCKLENS_EPOCH5_APPROVAL_SHA256"))==64,
             "EPOCH5_APPROVAL_PIN_MISSING")
    _require(event.get("mode")==PAPER and
             "session" not in event and
             "market" not in event,
             "SESSION_OR_MARKET_INJECTION_BLOCKED")
    import re
    approval_pin=os.getenv("STOCKLENS_EPOCH5_APPROVAL_SHA256","")
    _require(re.fullmatch(r"[0-9a-f]{64}",approval_pin) is not None,
             "EPOCH5_APPROVAL_SHA_INVALID")
    opening=adapter._market_clock(FIRST,"2026-11-21T23:00:00Z")[2]
    approval=adapter._approval(s3,FIRST,opening)
    _require(approval["sha256"]==approval_pin,"EPOCH5_APPROVAL_SHA_DRIFT")
    return prospective.run_current_session(
        s3,now=datetime.now(timezone.utc))

"""Isolated ST Epoch4 Lambda: live prospective modeled Paper only if armed.

Readiness dark mode remains no-write. Scheduled Paper never accepts event
dates or externally provided quotes: derive NYSE session from real UTC clock,
verify original preopen approval, strict Yahoo 1m bars, immutable S3 record
and prior continuity. Broker orders always disabled.
"""
from __future__ import annotations
from datetime import datetime, timezone
import os
from infra.aws import sl63_epoch4_paper_economic_adapter as adapter
from infra.aws import sl63_epoch4_prospective_runtime as prospective
from infra.aws import sl63_epoch4_immutable_store as store

REGION="eu-central-1"
FIRST="2026-11-19"
READINESS="STAGING_EPOCH4_DARK_READINESS"
PREFLIGHT="STAGING_EPOCH4_READ_ONLY_PREFLIGHT"
PAPER="STAGING_EPOCH4_MODELED_PAPER"
ST="stocklens-st-candidatedata-6jj7i9fxjmfr"


class DarkEpoch4Blocked(RuntimeError):
    pass


def _require(ok,reason):
    if not ok:raise DarkEpoch4Blocked(reason)


def handler(event,context):
    _require(type(event) is dict,"EVENT_OBJECT_REQUIRED")
    _require(os.getenv("STOCKLENS_DATA_BUCKET")==ST,
             "NOT_EXPECTED_ST_BUCKET")
    _require(os.getenv("AWS_REGION",REGION)==REGION,
             "REGION_DIFFERENT_FROM_ST_PIN")
    mode=event.get("mode")
    _require(mode in (READINESS,PREFLIGHT,PAPER),
             "UNKNOWN_MODE_FAIL_CLOSED")
    import boto3
    s3=boto3.client("s3",region_name=REGION)
    if mode in (READINESS,PREFLIGHT):
        if mode==READINESS:
            _require(os.getenv("STOCKLENS_EPOCH4_WRITE_ENABLED")=="false",
                     "READINESS_MUST_REMAIN_DARK")
        else:
            _require(os.getenv("STOCKLENS_EPOCH4_WRITE_ENABLED") in (
                "false","true"),"UNCONFIGURED_EPOCH4_WRITE_GATE")
        _,priorclose,opening,_=adapter._market_clock(
            FIRST,"2026-11-20T23:00:00Z")
        approval=adapter._approval(s3,FIRST,opening)
        prior,close,_,_=adapter._market_clock(
            FIRST,"2026-11-20T23:00:00Z")
        signal=adapter._source_signal(
            s3,FIRST,prior,close,opening,approval)
        return {
            "status":("EPOCH4_DARK_LAMBDA_READINESS_S3_READ_ONLY"
                      if mode==READINESS else
                      "EPOCH4_ARMED_READINESS_S3_READ_ONLY"),
            "epoch":store.EPOCH,
            "approval_sha256":approval["sha256"],
            "approved_prior_signal_sha256":signal["sha256"],
            "new_epoch_paper_or_continuity_written":False,
            "schedule_enabled":False,
            "broker_orders":False,
            "independently_qualified":False,
        }
    _require(os.getenv("STOCKLENS_EPOCH4_WRITE_ENABLED")=="true",
             "EPOCH4_WRITE_DISABLED_DARK_DEPLOYMENT")
    _require(os.getenv("STOCKLENS_EPOCH4_APPROVAL_SHA256")==
             "a7a0bf04760aa3d7ca83117b434bc13e7a63db785caff190123339a331afd27d",
             "EPOCH4_APPROVAL_PIN_MISSING")
    _require(event.get("mode")==PAPER and
             "session" not in event and
             "market" not in event,
             "SESSION_OR_MARKET_INJECTION_BLOCKED")
    return prospective.run_current_session(
        s3,now=datetime.now(timezone.utc))

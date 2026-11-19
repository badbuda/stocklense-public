"""Isolated ST Epoch4 Lambda. DARK by default; NO scheduler, NO broker.

This is a deployable, strict entry point separate from the legacy Paper
Lambda. Dark mode performs read-only S3 approval/lag1 pin checks. Modeled Paper
writes are DISABLED at the environment gate until a separate guarded release
after vendor and new Epoch4 continuity acceptance.
"""
from __future__ import annotations

from datetime import datetime, timezone
import os

from infra.aws import sl63_epoch4_paper_economic_adapter as adapter
from infra.aws import sl63_epoch4_immutable_store as store
from stocklens import paper as model

REGION="eu-central-1"
FIRST="2026-11-19"
READINESS="STAGING_EPOCH4_DARK_READINESS"
PAPER="STAGING_EPOCH4_MODELED_PAPER"
ST="stocklens-st-candidatedata-6jj7i9fxjmfr"


class DarkEpoch4Blocked(RuntimeError):
    pass


def _require(value,reason):
    if not value:
        raise DarkEpoch4Blocked(reason)


def _session(event):
    d=event.get("session")
    _require(isinstance(d,str),"SESSION_REQUIRED")
    store.validate_session(d)
    return d


def handler(event,context):
    _require(isinstance(event,dict),"EVENT_OBJECT_REQUIRED")
    _require(os.getenv("STOCKLENS_DATA_BUCKET")==ST,
             "NOT_EXPECTED_ST_BUCKET")
    _require(os.getenv("AWS_REGION",REGION)==REGION,
             "REGION_DIFFERENT_FROM_ST_PIN")
    import boto3
    s3=boto3.client("s3",region_name=REGION)
    mode=event.get("mode")

    if mode==READINESS:
        _require(os.getenv("STOCKLENS_EPOCH4_WRITE_ENABLED")=="false",
                 "READINESS_MUST_REMAIN_DARK")
        # Pin original operator approval and prior signal, no writes.
        _,_,opening,_=adapter._market_clock(
            FIRST,"2026-11-20T23:00:00Z")
        approval=adapter._approval(s3,FIRST,opening)
        prior,close,_,_=adapter._market_clock(
            FIRST,"2026-11-20T23:00:00Z")
        signal=adapter._source_signal(
            s3,FIRST,prior,close,opening,approval)
        return {
            "status":"EPOCH4_DARK_LAMBDA_READINESS_S3_READ_ONLY",
            "epoch":store.EPOCH,
            "approval_sha256":approval["sha256"],
            "approved_prior_signal_sha256":signal["sha256"],
            "legacy_paper_lambda_untouched":True,
            "new_epoch_paper_or_continuity_written":False,
            "broker_orders":False,
            "schedule_enabled":False,
            "independently_qualified":False,
        }

    if mode==PAPER:
        # Enabled only via a separate future CloudFormation release with
        # validated market source, watchdog and explicit operator approval.
        _require(os.getenv("STOCKLENS_EPOCH4_WRITE_ENABLED")=="true",
                 "EPOCH4_WRITE_DISABLED_DARK_DEPLOYMENT")
        session=_session(event)
        # NEVER permit event-specified historical catchup. A release later
        # must prove that the designated session was prospectively observable.
        _require(event.get("operator_release_attested") is True,
                 "OPERATOR_RELEASE_ATTESTATION_REQUIRED")
        now=datetime.now(timezone.utc)
        prior,_,_,_ = adapter._market_clock(session,now)
        market=model.fetch_execution_market(prior,session)
        return adapter.build_and_store_pair(
            s3,session=session,market=market,observed_at_utc=now)

    raise DarkEpoch4Blocked("UNKNOWN_MODE_FAIL_CLOSED")

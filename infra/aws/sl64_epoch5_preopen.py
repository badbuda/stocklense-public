#!/usr/bin/env python3
"""Forward-only preopen inception approval for NEW Epoch5 Nov20 ST book.

The original Nov19 Epoch4 book was only deployed DARK and never produced real
Paper. It is NEVER backfilled. A brand-new empty $100k SHADOW book may open on
Nov20 only with the Nov19 frozen signal stored in real versioned ST S3 *after*
Nov19 close and *before* Nov20 opening. The operator explicitly runs
--approve-new-epoch5. No broker, no Genesis/Paper/Continuity or schedule writes.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import hashlib
import json
import re

from infra.aws import sl56_epoch4_approval_readback as old
from infra.aws import sl64_epoch5_paper_economic_adapter as adapter
from infra.aws import sl64_epoch5_immutable_store as store

REGION="eu-central-1"
ACCOUNT="634740393398"
BUCKET=store.ST_BUCKET
FIRST="2026-11-20"
SOURCE="signals/2026-11-19.json"
KEY=store.PREFIX+"preopen-inception-approval.json"
APPROVAL_SCHEMA="stocklens-epoch5-preopen-inception-intent-v1"


class PreopenNotEligible(RuntimeError):
    pass


def require(ok,reason):
    if not ok:raise PreopenNotEligible(reason)


def preflight(sts,s3,*,now):
    now=adapter._time(now)
    require(sts.get_caller_identity().get("Account")==ACCOUNT,
            "WRONG_AWS_ACCOUNT")
    require(s3.get_bucket_versioning(Bucket=BUCKET).get("Status")=="Enabled",
            "ST_S3_VERSIONING_REQUIRED")
    prior,prior_close,opening,_=adapter._market_clock(
        FIRST,"2026-11-21T23:00:00Z")
    require(prior=="2026-11-19","EXPECTED_PREVIOUS_NYSE_SESSION_CHANGED")
    signal=adapter._verified(s3,SOURCE)
    p=signal["payload"]
    require(p.get("mode")=="SHADOW_ONLY_NO_BROKER_ACTIONS"
            and p.get("execution_plan",{}).get("broker_actions_enabled") is False
            and p.get("latest",{}).get("asof_date")==prior,
            "NO_QUALIFIED_NOV19_LAG1_SIGNAL")
    generated=adapter._time(p.get("generated_at_utc"))
    require(prior_close<=generated<opening
            and prior_close<=signal["saved_utc"]<opening,
            "NOV19_SIGNAL_NOT_FROZEN_AFTER_CLOSE_BEFORE_OPEN")
    latest=p.get("latest") or {}
    require(latest.get("defense_active") in (True,False)
            and latest.get("target_leverage") is not None,
            "SIGNAL_TARGET_NOT_VERIFIABLE")
    for name in ("qqq_weight","tqqq_weight"):
        x=latest.get(name)
        require(type(x) in (float,int) and 0<=x<=1,
                "INVALID_FROZEN_WEIGHTS")
    require(latest["qqq_weight"]+latest["tqqq_weight"]<=1.00000001,
            "FROZEN_WEIGHT_SUM_EXCEEDS_ONE")
    doc={
       "schema":APPROVAL_SCHEMA,
       "book":store.EPOCH,
       "first_session":FIRST,
       "prior_signal_key":signal["key"],
       "prior_signal_version_id":signal["version_id"],
       "prior_signal_sha256":signal["sha256"],
       "starting_cash_usd":100000.0,
       "starting_shares":{"QQQ":0,"TQQQ":0},
       "old_nav_transferred":False,
       "previous_epoch4_book_not_backfilled":True,
       "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
       "broker_orders_authorized":False,
       "genesis_created":False,
       "paper_trades_created":False,
    }
    # Inspect can remain read-only after the opening; new creation cannot.
    return {
       "status":"EPOCH5_SOURCE_ST_LAG1_VERIFIED",
       "book":store.EPOCH,"source_key":signal["key"],
       "source_version":signal["version_id"],
       "source_sha256":signal["sha256"],
       "first_session":FIRST,"prior_close_utc":prior_close.isoformat(),
       "opening_utc":opening.isoformat(),"time_is_preopen":now<opening,
       "preopen_approval_new_write_eligible":prior_close<=now<opening,
       "document":doc,
       "source_attestation":"SINGLE_VERSIONED_ST_SIGNAL_NOT_NEW_MARKET_DATA",
    }


def approve(sts,s3,*,now,enabled):
    check=preflight(sts,s3,now=now)
    doc=check.pop("document")
    raw=store.canonical(doc)
    sha=hashlib.sha256(raw).hexdigest()
    if not enabled:
        return {**check,
                "status":"EPOCH5_APPROVAL_PREFLIGHT_READONLY",
                "proposed_approval_sha256":sha,
                "aws_mutations":False,
                "paper_written":False}
    require(check["preopen_approval_new_write_eligible"],
            "EPOCH5_PREOPEN_WINDOW_CLOSED_OR_NOT_YET_ELIGIBLE")
    already=False
    try:
        s3.put_object(Bucket=BUCKET,Key=KEY,Body=raw,
                      ContentType="application/json",IfNoneMatch="*",
                      Metadata={"sha256":sha,"schema":APPROVAL_SCHEMA})
    except Exception as exc:
        code=(getattr(exc,"response",{}) or {}).get("Error",{}).get("Code")
        require(code in ("412","PreconditionFailed"),
                "S3_APPROVAL_PUT_UNCERTAIN_REVIEW_REQUIRED")
        already=True
    head=s3.head_object(Bucket=BUCKET,Key=KEY)
    require(head.get("ContentLength")==len(raw)
            and (head.get("Metadata") or {}).get("sha256")==sha,
            "APPROVAL_S3_HEADER_DRIFT")
    version=head.get("VersionId")
    require(isinstance(version,str) and version not in ("","null"),
            "APPROVAL_S3_VERSION_REQUIRED")
    require(adapter._time(head.get("LastModified"))<adapter._time(
            check["opening_utc"]),
            "APPROVAL_S3_LAST_MODIFIED_AFTER_FIRST_OPEN")
    obj=s3.get_object(Bucket=BUCKET,Key=KEY,VersionId=version)
    require(obj.get("VersionId")==version and
            obj["Body"].read(store.MAX_BYTES+1)==raw,
            "APPROVAL_EXACT_PINNED_S3_READBACK_FAILED")
    return {**check,
        "status":"EPOCH5_PREOPEN_APPROVAL_STORED_AND_VERSION_VERIFIED",
        "approval_key":KEY,
        "approval_sha256":sha,
        "approval_version_id":version,
        "new_approval_written":not already,
        "aws_mutations":not already,
        "new_epoch_genesis_or_paper_written":False,
        "broker_orders":False,
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--approve-new-epoch5",action="store_true")
    args=p.parse_args()
    import boto3
    sdk=boto3.session.Session(region_name=REGION)
    try:
        result=approve(sdk.client("sts"),sdk.client("s3"),
                       now=datetime.now(timezone.utc),
                       enabled=args.approve_new_epoch5)
        rc=0
    except Exception as exc:
        result={"status":"EPOCH5_PREOPEN_SOURCE_OR_APPROVAL_BLOCKED",
                "error_type":type(exc).__name__,
                "reason":str(exc)[:240],
                "paper_written":False,"broker_orders":False,
                "aws_mutation_state_uncertain":args.approve_new_epoch5}
        rc=4
    print(json.dumps(result,indent=2,sort_keys=True))
    return rc


if __name__=="__main__":
    raise SystemExit(main())

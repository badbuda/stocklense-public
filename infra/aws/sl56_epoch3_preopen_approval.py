#!/usr/bin/env python3
"""ST ONLY: explicit pre-open consent for proposed NEW Paper simulation book.

Creates one immutable versioned approval object under isolated new prefix.
No Paper Genesis, no trading, no S3 old-book writes, no alarms disabled.
An operator must explicitly run --approve-preopen-cash-100000 BEFORE
2026-11-12T14:30:00Z. If missed, use a fresh later epoch; do not backdate.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import sys

from infra.aws import sl56_epoch3_readonly_preflight as check
from stocklens import epoch3_store


def main(argv=None):
    p=argparse.ArgumentParser()
    p.add_argument("mode",choices=("inspect","approve"))
    p.add_argument("--approve-preopen-cash-100000",action="store_true")
    args=p.parse_args(argv)
    if args.mode=="approve":
        check.require(args.approve_preopen_cash_100000,
                      "EXPLICIT_OPERATOR_INCEPTION_APPROVAL_REQUIRED")
    else:
        check.require(not args.approve_preopen_cash_100000,
                      "READ_ONLY_INSPECT_CANNOT_APPROVE")
    import boto3
    session=boto3.Session(region_name=check.REGION)
    c={name:session.client(name) for name in
       ("sts","cloudformation","events","lambda","s3")}
    report=check.preflight(c)
    report["intent_mode"]=args.mode
    print(json.dumps(report,sort_keys=True,default=str),flush=True)
    if args.mode=="inspect":
        return 0
    def revalidate_before_write():
        check.preflight(c)
        return None
    book=epoch3_store.Epoch3Store(
        c["s3"],bucket=check.BUCKET,
        verify_before_each_write=revalidate_before_write)
    result=book.approve_inception(
        explicit_operator_yes=True,starting_cash_usd=100000.0,
        now=datetime.now(timezone.utc))
    print(json.dumps({
        "status":result["status"],
        "approval_key":result["key"],
        "approval_sha256":result["sha256"],
        "versioned":result["versioned"],
        "s3_server_preopen_verified":result["server_timestamp_verified"],
        "new_genesis_created":False,
        "paper_trades_created":False,
        "historical_book_or_alarms_changed":False,
        "production_untouched":True,
        "broker_orders":False,
    },sort_keys=True),flush=True)
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status":"ST_EPOCH3_PREOPEN_APPROVAL_BLOCKED_OR_PARTIAL_REVIEW_REQUIRED",
                          "reason":str(exc)[:240],
                          "no_broker":True,
                          "production_untouched":True}),file=sys.stderr)
        raise SystemExit(2)

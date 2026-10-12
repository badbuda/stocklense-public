#!/usr/bin/env python3
"""Read-only, independent consistency audit of staged AWS Paper receipts.

No GitHub/network quotes/broker. Only S3 reads, historical modeled ledger
reconstruction and SHA-256 chain checking.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import date
import hashlib
import json
import os
import sys

import boto3
from paper_portfolio_integrity import evaluate
from infra.aws.independent_paper import (
    AUDIT_PASS, BOOK, MAX_RECEIPT, previous_xnys_session
)
from infra.aws.independent_pipeline import canonical


def verified_get(s3, bucket: str, key: str):
    obj = s3.get_object(Bucket=bucket, Key=key)
    if not obj.get("VersionId") or obj["VersionId"] == "null":
        raise RuntimeError("NONVERSIONED_S3_PROOF:" + key)
    raw = obj["Body"].read(MAX_RECEIPT + 1)
    if len(raw) > MAX_RECEIPT:
        raise RuntimeError("S3_RECEIPT_TOO_LARGE")
    return json.loads(raw), raw, obj["VersionId"]


def verify(*, session: str, s3, bucket: str):
    prior = previous_xnys_session(session)
    paper, paper_raw, paper_version = verified_get(
        s3, bucket, f"paper/sessions/{session}.json"
    )
    market, market_raw, market_version = verified_get(
        s3, bucket, f"market/paper/{session}.json"
    )
    previous_signal, prev_signal_raw, signal_version = verified_get(
        s3, bucket, f"signals/{prior}.json"
    )
    current_signal, current_signal_raw, current_version = verified_get(
        s3, bucket, f"signals/{session}.json"
    )
    if paper["book"] != BOOK or paper["session"] != session:
        raise RuntimeError("PAPER_BOOK_OR_SESSION_MISMATCH")
    if paper["market_version_id"] != market_version:
        raise RuntimeError("MARKET_VERSION_MISMATCH")
    if paper["market_sha256"] != hashlib.sha256(
        canonical(market["observed_values"])
    ).hexdigest():
        raise RuntimeError("PAPER_OBSERVED_MARKET_SHA_MISMATCH")
    if paper["current_signal_sha256"] != hashlib.sha256(current_signal_raw).hexdigest():
        raise RuntimeError("CURRENT_SIGNAL_SHA_MISMATCH")
    if paper["prior_signal_sha256"] != hashlib.sha256(prev_signal_raw).hexdigest():
        raise RuntimeError("PRIOR_SIGNAL_SHA_MISMATCH")
    if market["prior_signal_version_id"] != signal_version:
        raise RuntimeError("SOURCE_PRIOR_SIGNAL_VERSION_MISMATCH")
    if market["current_signal_version_id"] != current_version:
        raise RuntimeError("SOURCE_CURRENT_SIGNAL_VERSION_MISMATCH")
    if current_signal["latest"]["asof_date"] != session:
        raise RuntimeError("CURRENT_SIGNAL_SESSION_MISMATCH")
    if previous_signal["latest"]["asof_date"] != prior:
        raise RuntimeError("PREVIOUS_SIGNAL_SESSION_MISMATCH")
    if paper["history"]["signal_snapshots"][prior] != previous_signal:
        raise RuntimeError("PAPER_SIGNAL_SNAPSHOT_MISMATCH")
    if paper["row"]["session_date"] != session:
        raise RuntimeError("PAPER_ROW_SESSION_MISMATCH")
    if paper["broker_orders_authorized"] is not False:
        raise RuntimeError("UNAUTHORIZED_BROKER_ORDERS")
    if paper["broker_fills_observed"] is not False:
        raise RuntimeError("UNPROVEN_BROKER_FILLS")
    if paper["production_replacement_authorized"] is not False:
        raise RuntimeError("UNAUTHORIZED_PRODUCTION_REPLACEMENT")
    if paper["trades"] != [
        t for t in paper["history"]["trades"] if t["execution_session"] == session
    ]:
        raise RuntimeError("SESSION_TRADE_LIST_MISMATCH")
    independently_evaluated = evaluate(
        paper["history"]["ledger"],
        paper["history"]["trades"],
        paper["history"]["signal_snapshots"]
    )
    if independently_evaluated != paper["integrity"] or independently_evaluated["status"] != AUDIT_PASS:
        raise RuntimeError("INDEPENDENT_ACCOUNTING_AUDIT_FAILED")
    if not (paper["history"]["ledger"] and
            paper["history"]["ledger"][-1] == paper["row"]):
        raise RuntimeError("LATEST_LEDGER_ROW_MISMATCH")
    if paper["state"]["last_mark_session"] != session:
        raise RuntimeError("PAPER_STATE_NOT_MARKED")
    if paper["state"]["cash"] != paper["row"]["cash"]:
        raise RuntimeError("CASH_STATE_ROW_DIVERGENCE")
    for symbol in ("QQQ", "TQQQ"):
        if paper["state"]["shares"][symbol] != paper["row"][symbol.lower()+"_shares"]:
            raise RuntimeError("HOLDINGS_STATE_ROW_DIVERGENCE")

    bootstrap = paper["bootstrap_start"] == session
    if bootstrap:
        if paper["prior_receipt_sha256"] is not None:
            raise RuntimeError("BOOTSTRAP_CONTAINS_PREVIOUS_RECEIPT")
    else:
        previous_paper, previous_raw, previous_version = verified_get(
            s3, bucket, f"paper/sessions/{prior}.json"
        )
        if paper["prior_receipt_sha256"] != hashlib.sha256(previous_raw).hexdigest():
            raise RuntimeError("PAPER_PREVIOUS_SHA_CHAIN_MISMATCH")
        if market["previous_receipt_version_id"] != previous_version:
            raise RuntimeError("PAPER_PREVIOUS_VERSION_MISMATCH")
        if previous_paper["session"] != prior:
            raise RuntimeError("PAPER_PREVIOUS_SESSION_MISMATCH")
    return {
        "status": "AWS_ONLY_PAPER_RECEIPT_VERIFIED",
        "session": session,
        "paper_sha256": hashlib.sha256(paper_raw).hexdigest(),
        "paper_version_id": paper_version,
        "market_receipt_sha256": hashlib.sha256(market_raw).hexdigest(),
        "accounting_status": independently_evaluated["status"],
        "audited_sessions": independently_evaluated["verified_paper_sessions"],
        "broker_orders_authorized": False,
        "broker_fills_observed": False,
        "vendor_raw_http_receipt_archived": False,
        "cross_vendor_parity_proven": False,
        "production_independence_proven": False,
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python infra/aws/verify_independent_paper.py YYYY-MM-DD")
    region = os.environ.get("AWS_REGION", "eu-central-1")
    cf = boto3.client("cloudformation", region_name=region)
    outputs = {
        x["OutputKey"]: x["OutputValue"]
        for x in cf.describe_stacks(
            StackName="stocklens-independent-staging"
        )["Stacks"][0]["Outputs"]
    }
    report = verify(
        session=sys.argv[1], s3=boto3.client("s3", region_name=region),
        bucket=outputs["CandidateDataBucket"]
    )
    print(json.dumps(report, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

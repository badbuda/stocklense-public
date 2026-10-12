#!/usr/bin/env python3
"""Verify AWS-only candidate receipt chain; read-only and fail closed.

Usage: python3 infra/aws/verify_independent_candidate.py YYYY-MM-DD
Does not invoke Lambda, fetch external sites, access GitHub or modify AWS.
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
from datetime import date

import boto3


def audit(session: str, *, s3, bucket: str) -> dict:
    if date.fromisoformat(session).isoformat() != session:
        raise RuntimeError("INVALID_SESSION")
    expected = {
        "market": f"market/qqq/{session}.csv",
        "manifest": f"manifests/qqq/{session}.json",
        "signal": f"signals/{session}.json",
    }
    items = {}
    for name, key in expected.items():
        obj = s3.get_object(Bucket=bucket, Key=key)
        version_id = obj.get("VersionId")
        if not version_id or version_id == "null":
            raise RuntimeError("VERSIONING_NOT_PRESENT:" + name)
        body = obj["Body"].read(3_000_001)
        if len(body) > 3_000_000:
            raise RuntimeError("OBJECT_TOO_LARGE:" + name)
        items[name] = {"version_id": version_id, "body": body,
                       "sha": hashlib.sha256(body).hexdigest()}
    manifest = json.loads(items["manifest"]["body"])
    report = json.loads(items["signal"]["body"])
    if (manifest["input_key"] != expected["market"]
        or manifest["input_version_id"] != items["market"]["version_id"]
        or manifest["sha256"] != items["market"]["sha"]):
        raise RuntimeError("MARKET_PROVENANCE_MISMATCH")
    if manifest["audit"]["csv_sha256"] != items["market"]["sha"]:
        raise RuntimeError("VENDOR_CSV_DIGEST_MISMATCH")
    if manifest["audit"]["last_session"] != session:
        raise RuntimeError("VENDOR_SESSION_MISMATCH")
    if report["latest"]["asof_date"] != session:
        raise RuntimeError("SIGNAL_SESSION_MISMATCH")
    if report["data_audit"]["source_sha256"] != items["market"]["sha"]:
        raise RuntimeError("SIGNAL_MARKET_SHA_MISMATCH")
    if report["mode"] != "SHADOW_ONLY_NO_BROKER_ACTIONS":
        raise RuntimeError("NON_SHADOW_SIGNAL")
    if report["execution_plan"]["broker_actions_enabled"] is not False:
        raise RuntimeError("BROKER_MODE_VIOLATION")
    if report["version"] != "8.0.2-shadow-completed-session-guard":
        raise RuntimeError("FROZEN_VERSION_MISMATCH")
    return {
        "status": "CANDIDATE_RECEIPTS_INTERNALLY_CONSISTENT",
        "session": session,
        "market_sha256": items["market"]["sha"],
        "signal_sha256": items["signal"]["sha"],
        "manifest_sha256": items["manifest"]["sha"],
        "broker_actions": False,
        "vendor_parity_proven": False,
        "production_independence_proven": False,
    }


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Pass exactly one session YYYY-MM-DD")
    region = os.environ.get("AWS_REGION", "eu-central-1")
    cf = boto3.client("cloudformation", region_name=region)
    stack = cf.describe_stacks(StackName="stocklens-independent-staging")["Stacks"][0]
    outputs = {o["OutputKey"]: o["OutputValue"] for o in stack["Outputs"]}
    result = audit(sys.argv[1], s3=boto3.client("s3", region_name=region),
                   bucket=outputs["CandidateDataBucket"])
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

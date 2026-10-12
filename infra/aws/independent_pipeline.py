"""Staged AWS-native QQQ->S3->frozen StockLens 8.0 signal pipeline.

No GitHub runtime access, broker, DynamoDB writes or production aliases.
Can be manually invoked only in the staging CloudFormation stack.
"""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone

from infra.aws.independent_market_ingest import ingest
from infra.aws.independent_signal_producer import build_signal


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _immutable_put(s3, bucket: str, key: str, body: bytes, content_type: str) -> str:
    """Replay an identical payload safely, reject every divergent overwrite."""
    from botocore.exceptions import ClientError
    try:
        res = s3.put_object(
            Bucket=bucket, Key=key, Body=body, ContentType=content_type,
            IfNoneMatch="*", ServerSideEncryption="AES256"
        )
        version_id = res.get("VersionId")
        if not version_id or version_id == "null":
            raise RuntimeError("S3_BUCKET_VERSIONING_REQUIRED")
        return version_id
    except ClientError as exc:
        if exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode") not in (409, 412):
            raise
        existing = s3.get_object(Bucket=bucket, Key=key)
        if hashlib.sha256(existing["Body"].read()).digest() != hashlib.sha256(body).digest():
            raise RuntimeError("DIVERGENT_IMMUTABLE_S3_OBJECT:" + key) from exc
        version_id = existing.get("VersionId")
        if not version_id or version_id == "null":
            raise RuntimeError("S3_BUCKET_VERSIONING_REQUIRED") from exc
        return version_id


def run(*, expected_session: str, now: datetime, s3, bucket: str,
        ingest_fn=ingest) -> dict:
    if now.tzinfo is None:
        raise RuntimeError("NAIVE_CLOCK")
    raw, audit = ingest_fn(expected_session, now=now)
    source_digest = hashlib.sha256(raw).hexdigest()
    if audit["csv_sha256"] != source_digest or audit["last_session"] != expected_session:
        raise RuntimeError("INGEST_MANIFEST_MISMATCH")
    if audit["provider"] != "YAHOO_CHART_PUBLIC_ENDPOINT":
        raise RuntimeError("UNKNOWN_INGEST_PROVIDER")

    # Build the entire signal from the vendor payload *before* any write.
    # Frozen core replay semantics are imported, never rewritten.
    report = build_signal(
        raw, now, source="YAHOO_CHART_ADJUSTED_QQQ", source_sha256=source_digest
    )
    if report["latest"]["asof_date"] != expected_session:
        raise RuntimeError("FROZEN_SIGNAL_SESSION_MISMATCH")
    if report["mode"] != "SHADOW_ONLY_NO_BROKER_ACTIONS":
        raise RuntimeError("SHADOW_MODE_ONLY")
    if report["execution_plan"]["broker_actions_enabled"] is not False:
        raise RuntimeError("BROKER_FORBIDDEN")

    input_key = f"market/qqq/{expected_session}.csv"
    input_version = _immutable_put(s3, bucket, input_key, raw, "text/csv")
    manifest = {
        "status": "VERIFIED",
        "note": "Checks vendor schema and exact completed session only; not independent vendor parity.",
        "data_type": "QQQ_ADJUSTED_DAILY",
        "provider": audit["provider"],
        "input_key": input_key,
        "input_version_id": input_version,
        "sha256": source_digest,
        "audit": audit,
    }
    # The first immutable receipt wins. Timestamped vendor receipt may differ
    # on retries, which is intentional fail-closed rather than silent revision.
    manifest_key = f"manifests/qqq/{expected_session}.json"
    manifest_version = _immutable_put(s3, bucket, manifest_key, canonical(manifest), "application/json")

    signal_body = canonical(report)
    signal_digest = hashlib.sha256(signal_body).hexdigest()
    signal_key = f"signals/{expected_session}.json"
    signal_version = _immutable_put(s3, bucket, signal_key, signal_body, "application/json")
    return {
        "status": "STAGED_SIGNAL_ARCHIVED",
        "session": expected_session,
        "market_key": input_key,
        "market_version_id": input_version,
        "market_sha256": source_digest,
        "manifest_key": manifest_key,
        "manifest_version_id": manifest_version,
        "signal_key": signal_key,
        "signal_version_id": signal_version,
        "signal_sha256": signal_digest,
        "broker_actions": False,
        "vendor_parity_proven": False,
    }


def handler(event, context):
    import boto3
    if event.get("mode") != "STAGING_ONLY":
        raise RuntimeError("STAGING_MODE_REQUIRED")
    session = event["expected_session"]
    bucket = os.environ["STOCKLENS_DATA_BUCKET"]
    return run(
        expected_session=session,
        now=datetime.now(timezone.utc),
        s3=boto3.client("s3"),
        bucket=bucket,
    )

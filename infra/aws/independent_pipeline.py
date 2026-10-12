"""Staged AWS-native QQQ->S3->frozen StockLens 8.0 signal pipeline.

No GitHub runtime access, broker, DynamoDB writes or production aliases.
Can be manually invoked only in the staging CloudFormation stack.
"""
from __future__ import annotations
import hashlib
import json
import os
from datetime import datetime, timezone

from infra.aws.independent_market_ingest import _vendor_request, NY
from infra.aws.independent_frozen_ingest import ingest_frozen_yfinance, PROVIDER as FROZEN_PROVIDER
from infra.aws.independent_signal_producer import build_signal


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _immutable_put(s3, bucket: str, key: str, body: bytes, content_type: str) -> str:
    """Replay an identical payload safely, reject every divergent overwrite."""
    try:
        res = s3.put_object(
            Bucket=bucket, Key=key, Body=body, ContentType=content_type,
            IfNoneMatch="*", ServerSideEncryption="AES256"
        )
        version_id = res.get("VersionId")
        if not version_id or version_id == "null":
            raise RuntimeError("S3_BUCKET_VERSIONING_REQUIRED")
        return version_id
    except Exception as exc:
        response = getattr(exc, "response", None)
        if not isinstance(response, dict) or response.get("ResponseMetadata", {}).get("HTTPStatusCode") not in (409, 412):
            raise
        existing = s3.get_object(Bucket=bucket, Key=key)
        if hashlib.sha256(existing["Body"].read()).digest() != hashlib.sha256(body).digest():
            raise RuntimeError("DIVERGENT_IMMUTABLE_S3_OBJECT:" + key) from exc
        version_id = existing.get("VersionId")
        if not version_id or version_id == "null":
            raise RuntimeError("S3_BUCKET_VERSIONING_REQUIRED") from exc
        return version_id


def _existing_object(s3, bucket: str, key: str, limit: int = 2_000_000):
    """Read an existing immutable object, or None only on actual NotFound."""
    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
    except KeyError:
        return None  # Allows strict in-memory S3 test doubles.
    except Exception as exc:
        response = getattr(exc, "response", {})
        if isinstance(response, dict) and response.get("Error", {}).get("Code") in (
            "NoSuchKey", "404", "NotFound"
        ):
            return None
        raise
    version = obj.get("VersionId")
    if not version or version == "null":
        raise RuntimeError("S3_VERSIONING_REQUIRED:" + key)
    data = obj["Body"].read(limit + 1)
    if len(data) > limit:
        raise RuntimeError("EXISTING_OBJECT_TOO_LARGE:" + key)
    return data, version


def run(*, expected_session: str, now: datetime, s3, bucket: str,
        ingest_fn=ingest_frozen_yfinance) -> dict:
    """Source-pinned canonical StockLens Signal; validate before first S3 write."""
    if now.tzinfo is None:
        raise RuntimeError("NAIVE_CLOCK")
    raw, audit = ingest_fn(expected_session, now=now)
    source_digest = hashlib.sha256(raw).hexdigest()
    if audit["csv_sha256"] != source_digest or audit["last_session"] != expected_session:
        raise RuntimeError("INGEST_MANIFEST_MISMATCH")
    if audit["provider"] != FROZEN_PROVIDER:
        raise RuntimeError("FROZEN_YFINANCE_SOURCE_REQUIRED")
    if (audit.get("source_path") != "stocklens.data.load_qqq_history"
        or audit.get("data_integrity_status") !=
           "FROZEN_YFINANCE_SOURCE_VERIFIED_NOT_INDEPENDENT_VENDOR"
        or not audit.get("reference_feature_window_sha256")):
        raise RuntimeError("FROZEN_SOURCE_PROVENANCE_MISSING")

    input_key = f"market/qqq/{expected_session}.csv"
    manifest_key = f"manifests/qqq/{expected_session}.json"
    signal_key = f"signals/{expected_session}.json"

    # Never rewrite an existing session even when old adjusted Yahoo prices
    # have been revised. Same-body retries are valid; divergent data abort.
    previous_market = _existing_object(s3, bucket, input_key)
    if previous_market is not None:
        prior_raw, _ = previous_market
        if hashlib.sha256(prior_raw).hexdigest() != source_digest:
            raise RuntimeError("DIVERGENT_IMMUTABLE_MARKET_REVISION")
    previous_manifest = _existing_object(s3, bucket, manifest_key)
    previous_signal = _existing_object(s3, bucket, signal_key)
    if (previous_manifest or previous_signal) and previous_market is None:
        raise RuntimeError("BROKEN_MARKET_ARCHIVE_CHAIN")
    if previous_signal and not previous_manifest:
        raise RuntimeError("SIGNAL_EXISTS_WITHOUT_MANIFEST")

    frozen_generation_time = now
    manifest = None
    if previous_manifest is not None:
        manifest = json.loads(previous_manifest[0])
        if not (
            manifest.get("input_key") == input_key
            and manifest.get("input_version_id") == previous_market[1]
            and manifest.get("sha256") == source_digest
            and manifest.get("status") == "VERIFIED"
            and manifest.get("provider") == FROZEN_PROVIDER
            and manifest.get("data_type") == "QQQ_ADJUSTED_DAILY"
            and manifest.get("audit", {}).get("reference_feature_window_sha256")
                == audit["reference_feature_window_sha256"]
        ):
            raise RuntimeError("PREVIOUS_MARKET_MANIFEST_DIVERGENCE")
        previous_retrieval = manifest["audit"]["retrieved_at_utc"]
        frozen_generation_time = datetime.fromisoformat(
            previous_retrieval.replace("Z", "+00:00")
        )
        if (frozen_generation_time.tzinfo is None
            or frozen_generation_time > now):
            raise RuntimeError("INVALID_PREVIOUS_MARKET_RECEIPT_TIMESTAMP")

    # Perform the frozen computational replay and check reference fingerprint
    # BEFORE creating any new immutable object. A bad provider/library must
    # never leave an orphaned market object in S3.
    report = build_signal(
        raw, frozen_generation_time,
        source=FROZEN_PROVIDER,
        source_sha256=source_digest,
    )
    if report["latest"]["asof_date"] != expected_session:
        raise RuntimeError("FROZEN_SIGNAL_SESSION_MISMATCH")
    if (report["data_audit"]["feature_window_sha256"]
        != audit["reference_feature_window_sha256"]):
        raise RuntimeError("FROZEN_SOURCE_FEATURE_FINGERPRINT_MISMATCH")
    if report["mode"] != "SHADOW_ONLY_NO_BROKER_ACTIONS":
        raise RuntimeError("SHADOW_MODE_ONLY")
    if report["execution_plan"]["broker_actions_enabled"] is not False:
        raise RuntimeError("BROKER_FORBIDDEN")

    # Only after all computations pass can immutable S3 changes start.
    input_version = _immutable_put(s3, bucket, input_key, raw, "text/csv")
    if manifest is not None:
        if input_version != previous_market[1]:
            raise RuntimeError("INPUT_VERSION_CHANGED_DURING_RETRY")
    else:
        manifest = {
            "status": "VERIFIED",
            "note": (
                "Canonical original yfinance QQQ auto_adjust=True loader, "
                "completed NYSE session and original reference fingerprint; "
                "NOT independently verified vendor or point-in-time prices."
            ),
            "data_type": "QQQ_ADJUSTED_DAILY",
            "provider": FROZEN_PROVIDER,
            "input_key": input_key,
            "input_version_id": input_version,
            "sha256": source_digest,
            "audit": audit,
        }

    manifest_version = _immutable_put(
        s3, bucket, manifest_key, canonical(manifest), "application/json"
    )
    signal_body = canonical(report)
    signal_digest = hashlib.sha256(signal_body).hexdigest()
    signal_version = _immutable_put(
        s3, bucket, signal_key, signal_body, "application/json"
    )
    if previous_signal is not None and (
        hashlib.sha256(previous_signal[0]).hexdigest() != signal_digest
        or previous_signal[1] != signal_version
    ):
        raise RuntimeError("STORED_FROZEN_SIGNAL_DIVERGENCE")
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
        "canonical_source": FROZEN_PROVIDER,
        "frozen_feature_window_sha256": audit["reference_feature_window_sha256"],
    }


def _vendor_network_probe(*, now: datetime, fetcher=None) -> dict:
    """Read-only Yahoo network connectivity check, allowed before market close.

    This does NOT validate a completed current session, certify numerical
    parity or publish a signal. All ingest/paper paths remain untouched.
    """
    if now.tzinfo is None:
        raise ValueError("NAIVE_VENDOR_PROBE_CLOCK")
    payload, upstream_digest = (fetcher or _vendor_request)(now=now)
    try:
        chart = payload["chart"]
        if chart.get("error") is not None:
            raise ValueError("VENDOR_PROBE_ERROR")
        series = chart["result"][0]
        meta = series["meta"]
        stamps = series["timestamp"]
        adjusted = series["indicators"]["adjclose"][0]["adjclose"]
        if meta.get("symbol") != "QQQ":
            raise ValueError("VENDOR_PROBE_WRONG_SYMBOL")
        if meta.get("exchangeTimezoneName") != "America/New_York":
            raise ValueError("VENDOR_PROBE_WRONG_TIMEZONE")
        if not isinstance(stamps, list) or len(stamps) < 300:
            raise ValueError("VENDOR_PROBE_TOO_FEW_BARS")
        if len(stamps) != len(adjusted):
            raise ValueError("VENDOR_PROBE_ARRAY_MISMATCH")
        last_day = datetime.fromtimestamp(int(stamps[-1]), NY).date()
        if last_day > now.astimezone(NY).date():
            raise ValueError("VENDOR_PROBE_FUTURE_BAR")
    except (KeyError, IndexError, TypeError, OverflowError) as exc:
        raise ValueError("VENDOR_PROBE_MALFORMED_CHART") from exc
    return {
        "status": "STAGING_VENDOR_NETWORK_OK",
        "component": "signal",
        "provider": "YAHOO_CHART_PUBLIC_ENDPOINT",
        "rows": len(stamps),
        "last_vendor_calendar_date": last_day.isoformat(),
        "latest_session_completed": False,
        "market_data_written": False,
        "broker_actions": False,
        "upstream_response_sha256": upstream_digest,
        "historical_parity_proven": False,
    }


def _import_smoke():
    # No network access, market-data fetch, S3 writes or broker calls.
    import importlib
    for package in ("stocklens.core", "boto3"):
        importlib.import_module(package)
    if not os.environ.get("STOCKLENS_DATA_BUCKET"):
        raise RuntimeError("STAGING_BUCKET_ENV_MISSING")
    return {"status": "STAGING_IMPORT_OK", "component": "signal",
            "broker_actions": False, "market_data_written": False}


def handler(event, context):
    if event.get("mode") == "STAGING_IMPORT_SMOKE":
        return _import_smoke()
    if event.get("mode") == "STAGING_VENDOR_NETWORK_PROBE":
        return _vendor_network_probe(now=datetime.now(timezone.utc))
    if event.get("mode") == "STAGING_SAME_VENDOR_PATH_PARITY":
        # No S3 writes, shadow Signal production, or paper execution.
        from infra.aws.source_parity import compare_live_paths
        return compare_live_paths(now=datetime.now(timezone.utc))
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

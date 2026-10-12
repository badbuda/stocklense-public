"""S3-only StockLens 8.0 signal producer. No GitHub, no broker, no synthetic prices.

Package this module alongside frozen stocklens/core.py and stocklens/shadow.py.
The upstream independent market-data ingestion is a separate required gate.
"""
from __future__ import annotations
import csv
import hashlib
import io
import json
import os
from datetime import datetime, timezone, time
from zoneinfo import ZoneInfo

from stocklens.core import replay_levels

NY = ZoneInfo("America/New_York")
MODE = "SHADOW_ONLY_NO_BROKER_ACTIONS"
VERSION = "8.0.2-shadow-completed-session-guard"


def build_signal(raw: bytes, now: datetime, *, source: str, source_sha256: str):
    if now.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    now = now.astimezone(timezone.utc)
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
    if not rows or not {"Date", "Close"} <= set(rows[0]):
        raise ValueError("REQUIRE_DATE_CLOSE_CSV")
    dates = [r["Date"] for r in rows]
    closes = [float(r["Close"]) for r in rows]
    if dates != sorted(set(dates)) or len(dates) < 300:
        raise ValueError("UNSORTED_DUPLICATE_OR_SHORT_HISTORY")
    if dates[0] > "2008-01-10":
        raise ValueError("INSUFFICIENT_PRESTART_WARMUP")
    ny = now.astimezone(NY)
    if dates[-1] >= ny.date().isoformat() and ny.time() < time(18, 0):
        raise ValueError("INCOMPLETE_MARKET_SESSION")
    decisions = replay_levels(closes, dates)
    latest, previous = decisions[-1], decisions[-2]
    action = "NO_CHANGE"
    if previous.target_leverage != latest.target_leverage:
        action = "REBALANCE_NEXT_SESSION"
    if previous.defense_active != latest.defense_active:
        action = "ENTER_CASH_NEXT_SESSION" if latest.defense_active else "EXIT_CASH_NEXT_SESSION"
    report = {
        "version": VERSION,
        "generated_at_utc": now.isoformat(),
        "mode": MODE,
        "signal_source": "QQQ_ADJUSTED_DAILY_CLOSE",
        "state_replay": "EXACT_FROM_2009_09_01_WITH_PRESTART_WARMUP",
        "latest": latest.to_dict(),
        "previous": previous.to_dict(),
        "action": action,
        "execution_plan": {
            "signal_basis": "LATEST_COMPLETED_QQQ_DAILY_CLOSE",
            "reductions": "NEXT_SESSION_OPEN_PLUS_1_MIN",
            "additions": "NEXT_SESSION_OPEN_PLUS_2_MIN",
            "broker_actions_enabled": False,
        },
        "data_audit": {
            "rows": len(rows),
            "first_date": dates[0],
            "last_date": dates[-1],
            "last_close": closes[-1],
            "source": source,
            "source_sha256": source_sha256,
            "feature_window_sessions": 253,
        },
    }
    return report


def handler(event, context):
    import boto3
    bucket = os.environ["STOCKLENS_DATA_BUCKET"]
    input_key = event["input_key"]
    version = event["input_version_id"]
    if not input_key.startswith("market/qqq/") or not version:
        raise ValueError("VERSIONED_MARKET_INPUT_REQUIRED")
    s3 = boto3.client("s3")
    obj = s3.get_object(Bucket=bucket, Key=input_key, VersionId=version)
    raw = obj["Body"].read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("MARKET_INPUT_TOO_LARGE")
    sha = hashlib.sha256(raw).hexdigest()
    if sha != event["expected_input_sha256"]:
        raise ValueError("INPUT_SHA_MISMATCH")
    if event.get("independent_provider_verified") is not True:
        raise ValueError("INDEPENDENT_PROVIDER_NOT_VERIFIED")
    report = build_signal(raw, datetime.now(timezone.utc), source="S3_VERIFIED_QQQ_ADJUSTED", source_sha256=sha)
    session = report["latest"]["asof_date"]
    if session != event["expected_session"]:
        raise ValueError("SESSION_MISMATCH")
    payload = json.dumps(report, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    key = f"signals/{session}.json"
    # Conditional write prevents silent overwrites and does not touch live DynamoDB.
    s3.put_object(Bucket=bucket, Key=key, Body=payload, ContentType="application/json", IfNoneMatch="*",
                  Metadata={"source-sha256": sha, "signal-sha256": hashlib.sha256(payload).hexdigest()})
    return {"status": "STAGED_ONLY", "session": session, "key": key, "sha256": hashlib.sha256(payload).hexdigest(),
            "broker_actions": False}

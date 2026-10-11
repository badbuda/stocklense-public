"""Independent fail-closed verification of the AWS paper-only StockLens shadow journal.

This is an archive integrity check, NOT broker execution or paper-fill proof.
"""
from __future__ import annotations

import hashlib
import json
import math
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def _aware_iso(raw: str, code: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise ValueError(code) from exc
    if value.tzinfo is None:
        raise ValueError(code)
    return value.astimezone(timezone.utc)


def verify_journal_response(result: dict, expected_session: str) -> dict:
    try:
        if date.fromisoformat(expected_session).isoformat() != expected_session:
            raise ValueError()
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_EXPECTED_SESSION") from exc

    item = result.get("Item")
    if not isinstance(item, dict):
        raise ValueError("JOURNAL_SESSION_NOT_FOUND")
    stored_date = item.get("session_date", {}).get("S")
    if stored_date != expected_session:
        raise ValueError("JOURNAL_PRIMARY_KEY_MISMATCH")
    if item.get("broker_orders_authorized", {}).get("BOOL") is not False:
        raise ValueError("BROKER_EXECUTION_MUST_REMAIN_DISABLED")
    signal_raw = item.get("signal_json", {}).get("S")
    fingerprint = item.get("signal_sha256", {}).get("S")
    if not isinstance(signal_raw, str) or not signal_raw or len(signal_raw) > 100000:
        raise ValueError("INVALID_STORED_SIGNAL")
    observed = hashlib.sha256(signal_raw.encode("utf-8")).hexdigest()
    if fingerprint != observed:
        raise ValueError("SIGNAL_ARCHIVE_SHA256_MISMATCH")

    try:
        signal = json.loads(signal_raw)
    except json.JSONDecodeError as exc:
        raise ValueError("CORRUPTED_STORED_SIGNAL_JSON") from exc
    if not isinstance(signal, dict):
        raise ValueError("SIGNAL_NOT_OBJECT")
    if signal.get("mode") != "SHADOW_ONLY_NO_BROKER_ACTIONS":
        raise ValueError("NOT_SHADOW_ONLY")
    if signal.get("signal_source") != "QQQ_ADJUSTED_DAILY_CLOSE":
        raise ValueError("INVALID_SIGNAL_SOURCE")
    if signal.get("execution_plan", {}).get("broker_actions_enabled") is not False:
        raise ValueError("SIGNAL_BROKER_FLAG_NOT_DISABLED")
    if not str(signal.get("version", "")).startswith("8.0"):
        raise ValueError("FROZEN_VERSION_REQUIRED")
    latest = signal.get("latest", {})
    if latest.get("asof_date") != expected_session:
        raise ValueError("SIGNAL_ASOF_DATE_MISMATCH")
    if latest.get("level") not in (0, 1.25, 2, 3):
        raise ValueError("INVALID_FROZEN_LEVEL")
    weights = (latest.get("qqq_weight"), latest.get("tqqq_weight"))
    if any(
        isinstance(w, bool) or not isinstance(w, (int, float))
        or not math.isfinite(w) or not 0 <= w <= 1
        for w in weights
    ) or sum(weights) > 1.000001:
        raise ValueError("INVALID_TARGET_WEIGHTS")

    stored_at = _aware_iso(item.get("recorded_at_utc", {}).get("S"), "INVALID_JOURNAL_TIME")
    generated = _aware_iso(signal.get("generated_at_utc"), "INVALID_SIGNAL_TIME")
    if not timedelta(0) <= stored_at - generated <= timedelta(hours=18):
        raise ValueError("SIGNAL_WAS_NOT_FRESH_AT_RECORD_TIME")
    return {
        "status": "PASS_OBSERVED_ARCHIVED_SHADOW_SIGNAL",
        "asof": expected_session,
        "sha256": observed,
        "live_trading_authorized": False,
        "broker_fill_evidence": False,
    }


def main(path: str, session: str) -> None:
    response = json.loads(Path(path).read_text(encoding="utf-8"))
    report = verify_journal_response(response, session)
    print("AWS_SHADOW_JOURNAL=" + report["status"] + ";asof=" + report["asof"])
    print("AWS_STOCKLENS_LIVE_TRADING_AUTHORIZED=false")
    print("AWS_STOCKLENS_BROKER_FILL_EVIDENCE=false")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("Usage: python aws_shadow_journal_verify.py PATH YYYY-MM-DD")
    main(sys.argv[1], sys.argv[2])

"""AWS candidate prospective paper ledger, using unchanged frozen StockLens paper math.

At runtime the *existing* fetch_execution_market downloads observed raw Yahoo
1-minute QQQ/TQQQ bars via yfinance in AWS. The current and previous signals,
market snapshot, receipt and cumulative audit live only in versioned S3.
No GitHub, no broker, no retrospective fills and no implicit bootstrap.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, time, timezone
import hashlib
import json
import math
import os
from zoneinfo import ZoneInfo

from stocklens.paper import (
    SessionMarket,
    _apply_corporate_actions,
    fetch_execution_market,
    mark_session,
    new_state,
    rebalance_if_required,
)
from paper_portfolio_integrity import evaluate

from infra.aws.independent_pipeline import canonical, _immutable_put

NY = ZoneInfo("America/New_York")
SHADOW_MODE = "SHADOW_ONLY_NO_BROKER_ACTIONS"
AUDIT_PASS = "PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS"
BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK"
MAX_RECEIPT = 8_000_000


def previous_xnys_session(session: str) -> str:
    import exchange_calendars as xcals
    normalized = date.fromisoformat(session)
    if normalized.isoformat() != session:
        raise ValueError("NON_CANONICAL_SESSION_DATE")
    cal = xcals.get_calendar("XNYS")
    if not cal.is_session(session):
        raise ValueError("NOT_XNYS_SESSION")
    return cal.previous_session(session).date().isoformat()


def _timestamp(report: dict) -> datetime:
    ts = datetime.fromisoformat(report["generated_at_utc"].replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError("SIGNAL_TIMESTAMP_NAIVE")
    return ts.astimezone(timezone.utc)


def _checked_signal(report: dict, session: str, now: datetime):
    if report.get("mode") != SHADOW_MODE or not str(report.get("version", "")).startswith("8.0"):
        raise ValueError("FROZEN_SHADOW_SIGNAL_REQUIRED")
    if report.get("signal_source") != "QQQ_ADJUSTED_DAILY_CLOSE":
        raise ValueError("UNEXPECTED_SIGNAL_SOURCE")
    if report.get("execution_plan", {}).get("broker_actions_enabled") is not False:
        raise ValueError("BROKER_ACTIONS_PROHIBITED")
    if report.get("latest", {}).get("asof_date") != session:
        raise ValueError("SIGNAL_SESSION_MISMATCH")
    created = _timestamp(report)
    if created > now:
        raise ValueError("FUTURE_SIGNAL_GENERATION")
    target = report["latest"]
    if type(target.get("level")) is not int or target["level"] not in (1, 2, 3):
        raise ValueError("INVALID_FROZEN_LEVEL")
    if type(target.get("defense_active")) is not bool:
        raise ValueError("INVALID_FROZEN_DEFENSE")
    lev = target.get("target_leverage")
    expected = 0.0 if target["defense_active"] else {1: 1.25, 2: 2., 3: 3.}[target["level"]]
    if isinstance(lev, bool) or not isinstance(lev, (float, int)) or not math.isclose(lev, expected, abs_tol=1e-9):
        raise ValueError("INVALID_FROZEN_LEVERAGE")
    return created


def _checked_market(market: SessionMarket, expected: str):
    if market.session_date != expected or market.source != "YFINANCE_1M_RAW":
        raise ValueError("UNEXPECTED_OBSERVED_EXECUTION_SOURCE")
    for k in ("prices_0931", "prices_0932", "closes"):
        values = getattr(market, k)
        if set(values) != {"QQQ", "TQQQ"} or any(
            not math.isfinite(float(v)) or float(v) <= 0 for v in values.values()
        ):
            raise ValueError("INVALID_OBSERVED_MARKET:" + k)
    for k in ("dividends", "split_ratios"):
        values = getattr(market, k)
        if set(values) != {"QQQ", "TQQQ"} or any(
            not math.isfinite(float(v)) or float(v) < 0 for v in values.values()
        ):
            raise ValueError("INVALID_CORPORATE_ACTION:" + k)


def build_paper_receipt(
    *, session: str, current_signal: dict, prior_signal: dict,
    market: SessionMarket, now: datetime, previous_receipt: dict | None,
    previous_receipt_sha256: str | None = None, bootstrap: bool = False,
):
    """Deterministic pure frozen-math receipt; no fetching or S3 in this function."""
    if now.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    now = now.astimezone(timezone.utc)
    prior_day = previous_xnys_session(session)
    ny = now.astimezone(NY)
    if ny.date() < date.fromisoformat(session) or (
        ny.date() == date.fromisoformat(session) and ny.time() < time(18, 0)
    ):
        raise ValueError("PAPER_SESSION_NOT_COMPLETED")
    if (ny.date() - date.fromisoformat(session)).days > 5:
        raise ValueError("PAPER_SESSION_TOO_OLD")
    current_at = _checked_signal(current_signal, session, now)
    prior_at = _checked_signal(prior_signal, prior_day, now)
    open_at = datetime.combine(date.fromisoformat(session), time(9, 30), NY)
    if prior_at >= open_at.astimezone(timezone.utc):
        raise ValueError("PRIOR_SIGNAL_CREATED_AFTER_MARKET_OPEN")
    if current_at < open_at.astimezone(timezone.utc):
        raise ValueError("CURRENT_SIGNAL_PREDATES_SESSION")
    _checked_market(market, session)

    if previous_receipt is None:
        if bootstrap is not True or previous_receipt_sha256 is not None:
            raise ValueError("EXPLICIT_PROSPECTIVE_BOOTSTRAP_REQUIRED")
        state = new_state()
        ledger = []
        trades_history = []
        snapshots = {}
        bootstrap_start = session
    else:
        if bootstrap:
            raise ValueError("REBOOTSTRAP_NOT_ALLOWED")
        if not previous_receipt_sha256 or len(previous_receipt_sha256) != 64:
            raise ValueError("PREVIOUS_RECEIPT_SHA_REQUIRED")
        if previous_receipt.get("session") != prior_day or previous_receipt.get("book") != BOOK:
            raise ValueError("PAPER_CHAIN_GAP_OR_BOOK_MISMATCH")
        if previous_receipt.get("integrity", {}).get("status") != AUDIT_PASS:
            raise ValueError("PREVIOUS_PAPER_INTEGRITY_FAILED")
        state = deepcopy(previous_receipt["state"])
        if state.get("last_mark_session") != prior_day:
            raise ValueError("PREVIOUS_STATE_SESSION_MISMATCH")
        ledger = deepcopy(previous_receipt["history"]["ledger"])
        trades_history = deepcopy(previous_receipt["history"]["trades"])
        snapshots = deepcopy(previous_receipt["history"]["signal_snapshots"])
        if len(ledger) != previous_receipt["integrity"]["verified_paper_sessions"]:
            raise ValueError("PREVIOUS_HISTORY_LENGTH_MISMATCH")
        if not ledger or ledger[-1]["session_date"] != prior_day:
            raise ValueError("PREVIOUS_LEDGER_LAST_DAY_MISMATCH")
        if not math.isclose(state["cash"], ledger[-1]["cash"], rel_tol=0, abs_tol=1e-6):
            raise ValueError("PREVIOUS_CASH_MISMATCH")
        if any(state["shares"][s] != ledger[-1][s.lower()+"_shares"] for s in ("QQQ", "TQQQ")):
            raise ValueError("PREVIOUS_HOLDINGS_MISMATCH")
        bootstrap_start = previous_receipt["bootstrap_start"]

    if prior_day in snapshots and canonical(snapshots[prior_day]) != canonical(prior_signal):
        raise ValueError("DIVERGENT_PRIOR_SIGNAL_SNAPSHOT")
    snapshots[prior_day] = prior_signal
    actions = _apply_corporate_actions(state, market)
    trades = rebalance_if_required(
        state, prior_signal, market, bootstrap=previous_receipt is None
    )
    row = mark_session(
        state, prior_signal, market, trades, actions,
        bootstrap=previous_receipt is None
    )
    ledger.append(row)
    trades_history.extend(trades)
    integrity = evaluate(ledger, trades_history, snapshots)
    if integrity["status"] != AUDIT_PASS:
        raise RuntimeError("INDEPENDENT_FULL_LEDGER_AUDIT_FAILED:" +
                           ",".join(integrity.get("errors", [])))
    if integrity["latest_session"] != session or integrity["equity"] is None:
        raise RuntimeError("AUDIT_LAST_SESSION_MISMATCH")

    # This model estimates fills using observed minute-bar opens and assumed
    # costs; broker_fills_observed remains false in every S3 receipt.
    receipt = {
        "schema_version": 1,
        "session": session,
        "book": BOOK,
        "bootstrap_start": bootstrap_start,
        "mode": SHADOW_MODE,
        "signal_date": prior_day,
        "prior_receipt_sha256": previous_receipt_sha256,
        "market_sha256": hashlib.sha256(canonical(asdict(market))).hexdigest(),
        "row": row,
        "trades": trades,
        "state": state,
        "history": {
            "ledger": ledger,
            "trades": trades_history,
            "signal_snapshots": snapshots,
        },
        "integrity": integrity,
        "broker_orders_authorized": False,
        "broker_fills_observed": False,
        "production_replacement_authorized": False,
    }
    if len(canonical(receipt)) > MAX_RECEIPT:
        raise RuntimeError("PAPER_RECEIPT_TOO_LARGE_NEEDS_CHECKPOINTING")
    return receipt


def _s3_read(s3, bucket: str, key: str) -> tuple[bytes, str]:
    obj = s3.get_object(Bucket=bucket, Key=key)
    version_id = obj.get("VersionId")
    if not version_id or version_id == "null":
        raise RuntimeError("S3_VERSION_ID_REQUIRED:" + key)
    raw = obj["Body"].read(MAX_RECEIPT + 1)
    if len(raw) > MAX_RECEIPT:
        raise RuntimeError("S3_RECEIPT_TOO_LARGE:" + key)
    return raw, version_id


def run_paper(*, session: str, now: datetime, s3, bucket: str,
              bootstrap: bool = False, market_fetch=fetch_execution_market) -> dict:
    prior_day = previous_xnys_session(session)
    # Source contracts are read from immutable S3 objects (never GitHub).
    curr_raw, curr_version = _s3_read(s3, bucket, f"signals/{session}.json")
    prior_raw, prior_version = _s3_read(s3, bucket, f"signals/{prior_day}.json")
    current_signal, prior_signal = json.loads(curr_raw), json.loads(prior_raw)
    key_previous = f"paper/sessions/{prior_day}.json"
    try:
        previous_raw, previous_version = _s3_read(s3, bucket, key_previous)
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code not in ("NoSuchKey", "404", "NotFound"):
            raise
        previous_raw = None
        previous_version = None
    if bootstrap and previous_raw is not None:
        raise RuntimeError("PAPER_PREVIOUS_SESSION_EXISTS_CANNOT_BOOTSTRAP")
    if not bootstrap and previous_raw is None:
        raise RuntimeError("MISSING_PAPER_PREVIOUS_SESSION_FAIL_CLOSED")
    previous = json.loads(previous_raw) if previous_raw is not None else None

    market = market_fetch(prior_day, session)
    receipt = build_paper_receipt(
        session=session, current_signal=current_signal, prior_signal=prior_signal,
        market=market, now=now, previous_receipt=previous,
        previous_receipt_sha256=hashlib.sha256(previous_raw).hexdigest() if previous_raw else None,
        bootstrap=bootstrap
    )
    normalized_market = {
        "source": "YFINANCE_1M_RAW",
        "observed_values": asdict(market),
        "modelled_execution_not_broker_fills": True,
        "vendor_raw_http_response_archived": False,
        "current_signal_version_id": curr_version,
        "prior_signal_version_id": prior_version,
        "previous_receipt_version_id": previous_version,
    }
    market_body = canonical(normalized_market)
    market_sha = hashlib.sha256(canonical(asdict(market))).hexdigest()
    if market_sha != receipt["market_sha256"]:
        raise RuntimeError("MARKET_RECEIPT_FINGERPRINT_MISMATCH")
    market_key = f"market/paper/{session}.json"
    market_version = _immutable_put(s3, bucket, market_key, market_body, "application/json")
    receipt["market_key"] = market_key
    receipt["market_version_id"] = market_version
    receipt["current_signal_sha256"] = hashlib.sha256(curr_raw).hexdigest()
    receipt["prior_signal_sha256"] = hashlib.sha256(prior_raw).hexdigest()
    final = canonical(receipt)
    key = f"paper/sessions/{session}.json"
    version = _immutable_put(s3, bucket, key, final, "application/json")
    return {
        "status": "STAGED_PAPER_VERIFIED",
        "session": session,
        "book": BOOK,
        "paper_key": key,
        "paper_version_id": version,
        "paper_sha256": hashlib.sha256(final).hexdigest(),
        "equity": receipt["row"]["equity"],
        "trade_count": len(receipt["trades"]),
        "audit": receipt["integrity"]["status"],
        "broker_fills": False,
        "broker_orders": False,
    }


def _import_smoke():
    # Imports target native Linux wheels without an intraday provider request.
    import importlib
    for package in ("numpy", "pandas", "yfinance", "exchange_calendars",
                    "stocklens.paper", "paper_portfolio_integrity", "boto3"):
        importlib.import_module(package)
    if not os.environ.get("STOCKLENS_DATA_BUCKET"):
        raise RuntimeError("STAGING_BUCKET_ENV_MISSING")
    return {"status": "STAGING_IMPORT_OK", "component": "paper",
            "broker_actions": False, "market_data_written": False}


def handler(event, context):
    if event.get("mode") == "STAGING_IMPORT_SMOKE":
        return _import_smoke()
    import boto3
    if event.get("mode") != "STAGING_PAPER_ONLY":
        raise RuntimeError("STAGING_PAPER_MODE_REQUIRED")
    return run_paper(
        session=event["expected_session"],
        now=datetime.now(timezone.utc),
        s3=boto3.client("s3"),
        bucket=os.environ["STOCKLENS_DATA_BUCKET"],
        bootstrap=event.get("bootstrap") is True,
    )

"""Authenticated, strictly read-only StockLens journal API for HTTP API JWT route.

Never called without API Gateway Cognito JWT authorizer. No Scan, PutItem,
broker actions, Yahoo calls, synthetic backfills or IAM credentials in browser.
"""
import hashlib
import json
import os
import re
from datetime import date

_TABLE = None
KEY = re.compile(r"^20\d{2}-\d{2}-\d{2}$")


def json_response(code, body):
    return {"statusCode": code,
            "headers": {"content-type": "application/json",
                        "cache-control": "no-store, private"},
            "body": json.dumps(body, separators=(",", ":"))}


def require_dates(raw):
    if not isinstance(raw, str) or not raw:
        raise ValueError("MISSING_DATES")
    dates = raw.split(",")
    if len(dates) > 30 or len(dates) != len(set(dates)):
        raise ValueError("TOO_MANY_OR_DUPLICATE_DATES")
    for day in dates:
        if not KEY.fullmatch(day):
            raise ValueError("INVALID_DATE")
        try:
            if date.fromisoformat(day) > date.today():
                raise ValueError("FUTURE_SESSION")
        except ValueError as exc:
            raise ValueError("INVALID_DATE") from exc
    return sorted(dates)


def unpack(item, field, hash_field, day, kind):
    if item is None:
        return None
    if item.get("broker_orders_authorized") is not False:
        raise ValueError("BROKER_FLAG_DISALLOWED")
    if kind == "paper" and item.get("broker_fills_observed") is not False:
        raise ValueError("BROKER_FILL_CLAIM")
    raw, expected = item[field], item[hash_field]
    if hashlib.sha256(raw.encode()).hexdigest() != expected:
        raise ValueError("SHA256_MISMATCH")
    record = json.loads(raw)
    if kind == "signal":
        if record.get("mode") != "SHADOW_ONLY_NO_BROKER_ACTIONS":
            raise ValueError("SIGNAL_NOT_SHADOW")
        if record.get("latest", {}).get("asof_date") != day:
            raise ValueError("SIGNAL_DAY_MISMATCH")
    else:
        row, trades = record["row"], record.get("trs")
        if row.get("session_date") != day or row.get("execution_source") != "YFINANCE_1M_RAW":
            raise ValueError("INVALID_PAPER_SOURCE")
        if not isinstance(trades, list) or len(trades) != int(row["trade_count_session"]):
            raise ValueError("TRADE_COUNT_MISMATCH")
        if any(t.get("execution_session") != day for t in trades):
            raise ValueError("TRADE_DAY_MISMATCH")
    return record


def read_session(day, getter):
    try:
        signal = getter(day)
        paper = getter(day + "#PAPER")
        s = unpack(signal, "signal_json", "signal_sha256", day, "signal")
        p = unpack(paper, "paper_evidence_json", "paper_sha256", day, "paper")
        status = "PASS" if s and p else "MISSING_SIGNAL" if p else "MISSING_PAPER" if s else "MISSING_BOTH"
        return {
            "session_date": day, "status": status,
            "signal": {"level": s["latest"]["level"],
                       "target_leverage": s["latest"]["target_leverage"],
                       "recorded_at_utc": signal.get("recorded_at_utc", ""),
                       "sha256": signal["signal_sha256"]} if s else None,
            "paper": {"row": p["row"], "trades": p["trs"],
                      "recorded_at_utc": paper.get("recorded_at_utc", ""),
                      "sha256": paper["paper_sha256"]} if p else None,
        }
    except (KeyError, ValueError, TypeError, json.JSONDecodeError):
        return {"session_date": day, "status": "INVALID_EVIDENCE",
                "signal": None, "paper": None}


def handler(event, context):
    if event.get("requestContext", {}).get("http", {}).get("method") != "GET":
        return json_response(405, {"error": "METHOD_NOT_ALLOWED"})
    try:
        days = require_dates((event.get("queryStringParameters") or {}).get("dates"))
    except ValueError as exc:
        return json_response(400, {"error": str(exc)})
    global _TABLE
    if _TABLE is None:
        import boto3
        _TABLE = boto3.resource("dynamodb").Table(os.environ["JOURNAL_TABLE"])
    def get(key):
        data = _TABLE.get_item(Key={"session_date": key}, ConsistentRead=True)
        return data.get("Item")
    return json_response(200, {
        "kind": "STOCKLENS_AUTHENTICATED_READ_ONLY_AWS_JOURNAL",
        "sessions": [read_session(day, get) for day in days],
        "source": "DYNAMODB_GETITEM_SHA_VERIFIED",
        "broker_orders_authorized": False,
        "broker_fills_observed": False,
    })

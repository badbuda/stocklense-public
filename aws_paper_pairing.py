"""Read-only observed AWS shadow -> next-session modeled paper pairing.

Uses archived DynamoDB GetItem receipts; NEVER produces an order or classifies
local SHA-consistency as independent price/fill or prospective alpha evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from aws_journal_export import decode_paper, decode_signal

NY = ZoneInfo("America/New_York")


def _utc_timestamp(value, label):
    if not isinstance(value, str):
        raise ValueError(label + "_MISSING")
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(label + "_INVALID") from exc
    if ts.tzinfo is None:
        raise ValueError(label + "_NOT_TIMEZONE_AWARE")
    return ts.astimezone(timezone.utc)


def previous_session(day: str) -> str:
    try:
        parsed = date.fromisoformat(day)
        if parsed.isoformat() != day:
            raise ValueError()
        cal = xcals.get_calendar("XNYS")
        if not cal.is_session(day):
            raise ValueError()
        return cal.previous_session(day).date().isoformat()
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("PAIR_INVALID_XNYS_EXECUTION_SESSION") from exc


def verify_pair(session: str, prior_item: dict | None, paper_item: dict | None) -> dict:
    """Only a constrained *modeled* next-session pairing, not fills or live approval."""
    prior_day = previous_session(session)
    if prior_item is None:
        raise ValueError("PAIR_PRIOR_SIGNAL_ARCHIVE_MISSING")
    if paper_item is None:
        raise ValueError("PAIR_PAPER_ARCHIVE_MISSING")
    signal = decode_signal(prior_item, prior_day)
    paper = decode_paper(paper_item, session)
    prior_values = signal["value"]["latest"]
    row = paper["value"]["row"]
    if row.get("signal_date") != prior_day:
        raise ValueError("PAIR_PAPER_NOT_FROM_PREVIOUS_XNYS_SIGNAL")
    market_open = datetime.combine(
        date.fromisoformat(session), time(9, 30), tzinfo=NY
    ).astimezone(timezone.utc)
    archive_ts = _utc_timestamp(signal.get("recorded_at"), "PAIR_PRIOR_SIGNAL_ARCHIVE_TIME")
    if archive_ts >= market_open:
        raise ValueError("PAIR_PRIOR_SIGNAL_ARCHIVED_AFTER_NEXT_OPEN")
    for symbol in ("qqq", "tqqq"):
        source = prior_values.get(symbol + "_weight")
        target = row.get("target_" + symbol + "_weight")
        if (isinstance(source, bool) or isinstance(target, bool)
                or not isinstance(source, (int, float))
                or not isinstance(target, (int, float))
                or not math.isfinite(source) or not math.isfinite(target)
                or not 0 <= target <= 1
                or abs(float(source) - float(target)) > 1e-9):
            raise ValueError("PAIR_PREVIOUS_SIGNAL_TARGET_MISMATCH:" + symbol)
    for tr in paper["value"]["trs"]:
        if tr.get("signal_date") != prior_day:
            raise ValueError("PAIR_TRADE_NOT_FROM_PREVIOUS_XNYS_SIGNAL")
        expected_time = "09:31" if tr["side"] == "SELL" else "09:32"
        if tr.get("time_et") != expected_time:
            raise ValueError("PAIR_MODELED_TRADE_WINDOW_MISMATCH")
    pair_digest = hashlib.sha256(
        (signal["sha"] + ":" + paper["sha"]).encode("ascii")
    ).hexdigest()
    return {
        "status": "PASS_READ_ONLY_ARCHIVE_PAIRING_MODELED_NOT_BROKER_FILLS",
        "signal_session": prior_day,
        "execution_session": session,
        "model": "STOCKLENS_8_0_FROZEN",
        "prior_signal_sha256": signal["sha"],
        "paper_sha256": paper["sha"],
        "local_pair_digest_sha256": pair_digest,
        "qualified_independent_forward_session": False,
        "external_provider_quotes_verified": False,
        "broker_fills_observed": False,
        "capital_authorized": False,
        "automatic_trading_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", required=True)
    parser.add_argument("--prior-signal", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    args = parser.parse_args()
    prior = json.loads(args.prior_signal.read_text()).get("Item")
    paper = json.loads(args.paper.read_text()).get("Item")
    print(json.dumps(verify_pair(args.session, prior, paper), sort_keys=True))


if __name__ == "__main__":
    main()

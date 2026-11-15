"""Independent, read-only observed 1-minute coverage evidence for Paper gaps.

Never used as a fill/execution source. In particular, this module cannot
authorize a broker, publish a Paper receipt, replace Yahoo silently, or
fabricate missing minutes. A separate reviewed cross-provider integration
and explicit source provenance are required before any accounting use.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import math

REQUIRED_SYMBOLS = ("QQQ", "TQQQ")
MINIMUM_COVERAGE_TOLERANCE = 5


class MinuteCoverageError(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise MinuteCoverageError(reason)


def _utc(value):
    require(isinstance(value, str) and value.endswith("Z"),
            "BAR_TIMESTAMP_NOT_UTC_ISO_Z")
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MinuteCoverageError("INVALID_BAR_TIMESTAMP") from exc
    require(stamp.tzinfo is not None and
            stamp.utcoffset() == timedelta(0) and
            stamp.second == 0 and stamp.microsecond == 0,
            "BAR_TIMESTAMP_NOT_ALIGNED_MINUTE_UTC")
    return stamp


def audit_one(symbol, bars, session, *, calendar=None):
    """Observe coverage, no price interpolation, no synthetic bars.

    bars: Alpaca historical stock bars, with UTC t and raw o,c fields.
    Raises on malformed/duplicate/invalid OHLC. Insufficient coverage is
    reported as NOT QUALIFIED, never used as a filled Paper price.
    """
    require(symbol in REQUIRED_SYMBOLS, "SYMBOL_NOT_APPROVED")
    import exchange_calendars as xcals
    cal = calendar if calendar is not None else xcals.get_calendar("XNYS")
    require(cal.is_session(session), "NON_XNYS_SESSION")
    opening = cal.session_open(session).to_pydatetime().astimezone(timezone.utc)
    closing = cal.session_close(session).to_pydatetime().astimezone(timezone.utc)
    require(opening < closing and
            (closing-opening).total_seconds() % 60 == 0,
            "INVALID_EXCHANGE_SESSION_WINDOW")
    expected_count = int((closing-opening).total_seconds() // 60)
    require(expected_count in (210, 390), "UNEXPECTED_XNYS_SESSION_LENGTH")
    expected = [opening + timedelta(minutes=i) for i in range(expected_count)]
    expected_set = set(expected)
    observed = {}
    require(isinstance(bars, list), "ALPACA_BARS_NOT_LIST")
    for bar in bars:
        require(isinstance(bar, dict), "ALPACA_BAR_NOT_OBJECT")
        stamp = _utc(bar.get("t"))
        if stamp not in expected_set:
            continue  # Explicitly ignore pre/post market; never count them.
        require(stamp not in observed, "DUPLICATE_REGULAR_MINUTE_BAR")
        for field in ("o", "h", "l", "c"):
            value = bar.get(field)
            require(type(value) in (int, float) and
                    math.isfinite(value) and value > 0,
                    "INVALID_BAR_OHLC:" + field)
        require(bar["l"] <= min(bar["o"], bar["c"], bar["h"]) and
                bar["h"] >= max(bar["o"], bar["c"], bar["l"]),
                "INCONSISTENT_BAR_OHLC")
        observed[stamp] = bar

    missing = [stamp for stamp in expected if stamp not in observed]
    at31 = opening + timedelta(minutes=1)
    at32 = opening + timedelta(minutes=2)
    end = closing - timedelta(minutes=1)
    last_two = closing - timedelta(minutes=2)
    qualified = (len(observed) >= expected_count - MINIMUM_COVERAGE_TOLERANCE
                 and at31 in observed and at32 in observed
                 and end in observed and last_two in observed)
    observed_data = [
        [stamp.isoformat(), observed[stamp]["o"], observed[stamp]["h"],
         observed[stamp]["l"], observed[stamp]["c"]]
        for stamp in sorted(observed)
    ]
    digest = sha256(json.dumps(observed_data, separators=(",", ":"),
                               allow_nan=False).encode()).hexdigest()
    return {
        "status": ("COMPLETE_OBSERVED_MINUTES_RESEARCH_ONLY" if qualified
                   else "INCOMPLETE_OBSERVED_MINUTES_NO_PAPER"),
        "session": session,
        "symbol": symbol,
        "observed_regular_minute_bars": len(observed),
        "expected_regular_minute_bars": expected_count,
        "required_minimum_bars": expected_count - MINIMUM_COVERAGE_TOLERANCE,
        "missing_regular_minute_bars": len(missing),
        "missing_first_five_utc": [m.isoformat() for m in missing[:5]],
        "observed_0931": at31 in observed,
        "observed_0932": at32 in observed,
        "observed_final_two_minutes": last_two in observed and end in observed,
        "observed_values_sha256": digest,
        "requested_market_source": "ALPACA_HISTORICAL_SIP_1MIN_RAW",
        "source_entitlement_proven_by_response": False,
        "paper_accounting_authorized": False,
        "historical_backfill_authorized": False,
        "broker_orders_authorized": False,
        "s3_writes": False,
    }


def audit_pair(bars_by_symbol, session, *, calendar=None):
    require(isinstance(bars_by_symbol, dict) and
            set(bars_by_symbol) == set(REQUIRED_SYMBOLS),
            "REQUIRE_QQQ_AND_TQQQ_PAIR")
    both = {s: audit_one(s, bars_by_symbol[s], session, calendar=calendar)
            for s in REQUIRED_SYMBOLS}
    return {
        "status": ("RESEARCH_PAIR_COMPLETE_NOT_EXECUTION_AUTHORIZATION"
                   if all(v["status"] == "COMPLETE_OBSERVED_MINUTES_RESEARCH_ONLY"
                          for v in both.values())
                   else "RESEARCH_PAIR_INCOMPLETE_NO_PAPER"),
        "session": session,
        "per_symbol": both,
        "frozen_stocklens_8_0_unchanged": True,
        "deployed_runtime_unchanged": True,
        "paper_receipts_written": False,
        "historical_missed_sessions_requalified": False,
        "broker_orders_authorized": False,
    }

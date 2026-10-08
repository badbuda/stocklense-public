"""Append-only prospective observed QQQ/TQQQ 09:30/09:31/09:32 quotes.

No synthetic quotes. No historical backfill or reconstructed broker fills.
The first observation is created only for the session that just completed
on the CURRENT New York date after the official daily-bar safe cutoff.
This separate journal cannot authorize real trading.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
JOURNAL = Path("research/prospective/observed_intraday_etf_journal.jsonl")
REPORT = Path("docs/prospective_intraday_etf_journal.json")
SAFE_AFTER = time(18, 0)
CLOCK_KEYS = ("09:30", "09:31", "09:32")
SYMBOLS = ("QQQ", "TQQQ")


def _canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def read_rows(path=JOURNAL):
    p = Path(path)
    if not p.is_file():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            raise ValueError("EMPTY_PROSPECTIVE_JOURNAL_LINE")
        item = json.loads(line)
        rows.append(item)
    verify(rows)
    return rows


def verify(rows):
    prev_hash = "0" * 64
    last = ""
    for row in rows:
        day = row.get("session_date")
        if not isinstance(day, str) or day <= last:
            raise ValueError("DUPLICATE_OR_UNSORTED_SESSION")
        last = day
        if row.get("source") != "YFINANCE_OBSERVED_1MIN_RAW_OPEN":
            raise ValueError("NOT_OBSERVED_VENDOR_QUOTES")
        capture = datetime.fromisoformat(row["captured_at_utc"].replace("Z", "+00:00"))
        if capture.tzinfo is None:
            raise ValueError("NAIVE_CAPTURE_TIMESTAMP")
        ny = capture.astimezone(NY)
        if ny.date().isoformat() != day or ny.time() < SAFE_AFTER:
            raise ValueError("LATE_BACKFILL_OR_INCOMPLETE_SESSION")
        if row.get("prior_row_sha256") != prev_hash:
            raise ValueError("JOURNAL_HASH_CHAIN_BROKEN")
        for symbol in SYMBOLS:
            samples = row.get("quotes", {}).get(symbol, {})
            if set(samples) != set(CLOCK_KEYS):
                raise ValueError("MISSING_OBSERVED_MINUTE:" + symbol)
            if not all(isinstance(v, (float, int)) and math.isfinite(v) and v > 0
                       for v in samples.values()):
                raise ValueError("INVALID_PRICE:" + symbol)
        if row.get("synthetic_quotes_used") is not False or row.get("broker_fills_observed") is not False:
            raise ValueError("UNSUPPORTED_QUOTE_OR_BROKER_CLAIM")
        core = {k: v for k, v in row.items() if k != "row_sha256"}
        expected = hashlib.sha256(_canonical(core).encode()).hexdigest()
        if row.get("row_sha256") != expected:
            raise ValueError("ROW_INTEGRITY_MISMATCH")
        prev_hash = expected
    return prev_hash


def collect(prices, *, now=None, journal=JOURNAL):
    """Capture only today's fully completed session, never previous dates."""
    current = now or datetime.now(NY)
    if current.tzinfo is None:
        raise ValueError("NAIVE_CAPTURE_CLOCK")
    current = current.astimezone(NY)
    rows = read_rows(journal)
    day = current.date().isoformat()
    status = "WAITING_FOR_COMPLETED_SESSION"
    if current.time() >= SAFE_AFTER:
        last = rows[-1]["session_date"] if rows else None
        if last is not None and last >= day:
            if last != day:
                raise ValueError("JOURNAL_FUTURE_DATE_PRESENT")
            status = "ALREADY_CAPTURED_IMMUTABLE"
        else:
            quotes = {}
            for symbol in SYMBOLS:
                obs = prices.get(symbol, {}).get(day)
                if not isinstance(obs, dict) or any(key not in obs for key in CLOCK_KEYS):
                    quotes = {}
                    break
                vals = {k: float(obs[k]) for k in CLOCK_KEYS}
                if not all(math.isfinite(v) and v > 0 for v in vals.values()):
                    quotes = {}
                    break
                quotes[symbol] = vals
            if quotes and len(quotes) == len(SYMBOLS):
                row = {
                    "session_date": day,
                    "captured_at_utc": current.astimezone(timezone.utc).isoformat(),
                    "source": "YFINANCE_OBSERVED_1MIN_RAW_OPEN",
                    "quotes": quotes,
                    "prior_row_sha256": verify(rows),
                    "synthetic_quotes_used": False,
                    "broker_fills_observed": False,
                }
                row["row_sha256"] = hashlib.sha256(_canonical(row).encode()).hexdigest()
                verify(rows + [row])
                path = Path(journal)
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as fh:
                    fh.write(_canonical(row) + "\n")
                rows.append(row)
                status = "CAPTURED_NEW_VERIFIED_SESSION"
            else:
                status = "SOURCE_MINUTE_PRICES_UNAVAILABLE_NO_BACKFILL"
    return {
        "schema_version": 1, "status": status,
        "source": "YFINANCE_OBSERVED_1MIN_RAW_OPEN",
        "observed_completed_sessions": len(rows),
        "first_session": rows[0]["session_date"] if rows else None,
        "last_session": rows[-1]["session_date"] if rows else None,
        "journal_tail_sha256": verify(rows),
        "session_under_review": day,
        "daily_0931_0932_quotes_observed": bool(rows),
        "broker_fills_observed": False,
        "synthetic_quotes_used": False,
        "live_trading_authorized": False,
        "note": "Prospective same-day-after-close observed 1-minute ETF quotes only. Never inferred broker fills or reconstructed old missing bars.",
    }


def build(out=REPORT):
    from observed_intraday_execution_gap import fetch_minute_prices
    from pathlib import Path
    try:
        prices = fetch_minute_prices()
    except Exception:
        prices = {symbol: {} for symbol in SYMBOLS}
    result = collect(prices)
    target = Path(out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    build()

"""Canonical independent AWS-only QQQ ingestion using the frozen yfinance path.

This is NOT a second provider. It deliberately reproduces the data path used
by stocklens.data.load_qqq_history() in the existing frozen StockLens 8.0.
The separately staged Yahoo-chart direct reader remains read-only diagnostic.

No GitHub downloads, no Paper fills, no brokerage access or synthetic bars.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
PROVIDER = "YFINANCE_QQQ_AUTO_ADJUSTED"
SOURCE = "YFINANCE_QQQ_AUTO_ADJUSTED"
SAFE_AFTER = time(18, 0)
MAX_SESSION_AGE_DAYS = 5


def ingest_frozen_yfinance(expected_session: str, *, now: datetime | None = None,
                          loader=None):
    """Fetch and validate canonical QQQ prices from the unchanged old loader.

    Loader injection is only for offline tests. The deployed runtime always
    imports the frozen stocklens.data.load_qqq_history() implementation.
    """
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("CANONICAL_INGEST_NAIVE_CLOCK")
    ny = now.astimezone(NY)
    try:
        session = date.fromisoformat(expected_session)
    except (ValueError, TypeError) as exc:
        raise ValueError("CANONICAL_INGEST_INVALID_SESSION") from exc
    if session.isoformat() != expected_session:
        raise ValueError("CANONICAL_INGEST_NONCANONICAL_DATE")
    if session > ny.date() or (session == ny.date() and ny.time() < SAFE_AFTER):
        raise ValueError("CANONICAL_INGEST_SESSION_INCOMPLETE")
    if (ny.date() - session).days > MAX_SESSION_AGE_DAYS:
        raise ValueError("CANONICAL_INGEST_STALE_SESSION")

    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS")
    if not cal.is_session(expected_session):
        raise ValueError("CANONICAL_INGEST_NOT_XNYS_SESSION")

    if loader is None:
        from stocklens.data import load_qqq_history
        loader = load_qqq_history
    frame, audit = loader(now_ny=ny)
    if audit.get("source") != SOURCE:
        raise ValueError("CANONICAL_INGEST_FROZEN_SOURCE_REQUIRED")
    if len(frame) < 300 or not {"Date", "Close"} <= set(frame.columns):
        raise ValueError("CANONICAL_INGEST_MISSING_HISTORY")
    dates = [x.date().isoformat() for x in frame["Date"]]
    closes = [float(v) for v in frame["Close"]]
    if len(set(dates)) != len(dates) or dates != sorted(dates):
        raise ValueError("CANONICAL_INGEST_DUPLICATE_OR_UNSORTED")
    if dates[0] > "2008-01-10" or dates[-1] != expected_session:
        raise ValueError("CANONICAL_INGEST_STALE_OR_SHORT_HISTORY")
    if any(date.fromisoformat(d).weekday() > 4 for d in dates):
        raise ValueError("CANONICAL_INGEST_WEEKEND_VENDOR_BAR")
    if any(not math.isfinite(x) or x <= 0 for x in closes):
        raise ValueError("CANONICAL_INGEST_BAD_PRICE")
    if audit.get("completed_rows") != len(dates):
        raise ValueError("CANONICAL_INGEST_AUDIT_ROW_MISMATCH")
    if audit.get("last_completed_date") != expected_session:
        raise ValueError("CANONICAL_INGEST_AUDIT_LAST_SESSION_MISMATCH")

    # CSV float formatting is roundtrip-safe: it serializes the precise
    # observed Python float the frozen loader supplied, not a new adjustment.
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["Date", "Close"])
    writer.writerows((day, format(value, ".17g")) for day, value in zip(dates, closes))
    content = buffer.getvalue().encode("utf-8")

    # Prove that serialization retained the frozen loader's original
    # last-253-session fingerprint; never silently change its price series.
    from stocklens.data import _feature_window_sha256
    original_fp = _feature_window_sha256(frame, 253)
    serialized_fp = hashlib.sha256(
        "\n".join(
            f"{day},{float(value):.12g}"
            for day, value in zip(dates[-253:], closes[-253:])
        ).encode("utf-8")
    ).hexdigest()
    if original_fp != serialized_fp or audit.get("feature_window_sha256") != original_fp:
        raise ValueError("CANONICAL_INGEST_FROZEN_FINGERPRINT_MISMATCH")

    return content, {
        "provider": PROVIDER,
        "source_backend": "YAHOO_DATA_THROUGH_FROZEN_YFINANCE",
        "source_path": "stocklens.data.load_qqq_history",
        "symbol": "QQQ",
        "data_type": "QQQ_ADJUSTED_DAILY",
        "price_field": "yfinance.download(auto_adjust=True).Close",
        "exchange_timezone": "America/New_York",
        "retrieved_at_utc": now.astimezone(timezone.utc).isoformat(),
        "first_session": dates[0],
        "last_session": dates[-1],
        "row_count": len(dates),
        "csv_sha256": hashlib.sha256(content).hexdigest(),
        "reference_feature_window_sha256": original_fp,
        "reference_raw_rows": audit.get("raw_rows"),
        "reference_completed_rows": audit.get("completed_rows"),
        "reference_raw_last_date": audit.get("raw_last_date"),
        "reference_dropped_incomplete_current_session": audit.get(
            "dropped_incomplete_current_session"
        ),
        "vendor_raw_http_bytes_archived": False,
        "independent_quote_vendor_parity_proven": False,
        "data_integrity_status": "FROZEN_YFINANCE_SOURCE_VERIFIED_NOT_INDEPENDENT_VENDOR",
    }

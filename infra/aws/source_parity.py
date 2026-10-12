"""Read-only same-Yahoo, two-retrieval-path parity audit for frozen StockLens 8.0.

This compares Yahoo chart's adjusted closes with the original pinned
yfinance auto_adjust=True data path. Both depend on Yahoo; this is NOT an
independent data vendor audit and cannot certify order execution.

No S3 writes, synthetic bars, brokerage API calls or paper trades.
"""
from __future__ import annotations

import csv
import hashlib
import io
import math
from datetime import datetime, time
from zoneinfo import ZoneInfo

from infra.aws.independent_market_ingest import NY, _vendor_request, extract_adjusted_qqq
from infra.aws.independent_signal_producer import build_signal

MINIMUM_EXPECTED_DAYS = 300


def completed_xnys_session(now: datetime) -> str:
    """Most recent completed XNYS session; NY 18:00 cutoff, not local UTC."""
    if now.tzinfo is None:
        raise ValueError("SOURCE_PARITY_REQUIRES_AWARE_CLOCK")
    import exchange_calendars as xcals

    ny = now.astimezone(NY)
    cal = xcals.get_calendar("XNYS")
    candidate = cal.date_to_session(ny.date().isoformat(), direction="previous")
    if candidate.date() == ny.date() and ny.time() < time(18, 0):
        candidate = cal.previous_session(candidate)
    return candidate.date().isoformat()


def _completed_chart(payload: dict, *, now: datetime):
    """Drop only a still-open current-date chart bar for a read-only probe.

    We never drop a partially observed bar in a production archive writer.
    """
    ny = now.astimezone(NY)
    try:
        chart = payload["chart"]
        base = chart["result"][0]
        timestamps = base["timestamp"]
        prices = base["indicators"]["adjclose"][0]["adjclose"]
        if not timestamps or len(timestamps) != len(prices):
            raise ValueError("SOURCE_PARITY_CHART_SIZE_MISMATCH")
        last_day = datetime.fromtimestamp(int(timestamps[-1]), NY).date()
    except (KeyError, TypeError, IndexError, OverflowError) as exc:
        raise ValueError("SOURCE_PARITY_BAD_CHART") from exc
    dropped_partial_today = last_day == ny.date() and ny.time() < time(18, 0)
    if dropped_partial_today:
        timestamps = timestamps[:-1]
        prices = prices[:-1]
    minimal = {
        "chart": {
            "error": chart.get("error"),
            "result": [{
                "meta": base["meta"],
                "timestamp": timestamps,
                "indicators": {"adjclose": [{"adjclose": prices}]},
            }],
        },
    }
    return minimal, dropped_partial_today, last_day.isoformat()


def _feature_sha(dates: list[str], closes: list[float]) -> str:
    if len(dates) < 253:
        raise ValueError("NOT_ENOUGH_PARITY_FEATURE_SESSIONS")
    payload = "\n".join(
        f"{day},{float(close):.12g}"
        for day, close in zip(dates[-253:], closes[-253:])
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compare_completed_histories(
    *, vendor_raw: bytes, reference_df, expected_session: str, now: datetime
) -> dict:
    """Pure audit with an injected frozen yfinance result; no network or AWS."""
    vendor_rows = list(csv.DictReader(io.StringIO(vendor_raw.decode("utf-8-sig"))))
    v_dates = [r["Date"] for r in vendor_rows]
    v_closes = [float(r["Close"]) for r in vendor_rows]
    r_dates = [d.date().isoformat() for d in reference_df["Date"]]
    r_closes = [float(v) for v in reference_df["Close"]]

    if (len(v_dates) < MINIMUM_EXPECTED_DAYS
        or len(r_dates) < MINIMUM_EXPECTED_DAYS
        or v_dates[-1] != expected_session
        or r_dates[-1] != expected_session):
        raise ValueError("SOURCE_PARITY_INCOMPLETE_OR_STALE_LAST_SESSION")
    if (len(set(v_dates)) != len(v_dates) or v_dates != sorted(v_dates)
        or len(set(r_dates)) != len(r_dates) or r_dates != sorted(r_dates)):
        raise ValueError("SOURCE_PARITY_UNSORTED_OR_DUPLICATE_DATES")
    if any(not math.isfinite(x) or x <= 0 for x in v_closes + r_closes):
        raise ValueError("SOURCE_PARITY_NONPOSITIVE_OR_NONFINITE")

    calendars_match = v_dates == r_dates
    vendor_sha = _feature_sha(v_dates, v_closes)
    ref_sha = _feature_sha(r_dates, r_closes)
    differences = []
    if calendars_match:
        for d, v, r in zip(v_dates, v_closes, r_closes):
            if not math.isclose(v, r, abs_tol=1e-8, rel_tol=1e-8):
                differences.append((d, round(v, 8), round(r, 8)))
    else:
        # Do not compare misaligned closes or reindex missing market days away.
        differences = []
    matched = calendars_match and not differences and vendor_sha == ref_sha
    result = {
        "status": "STAGING_SAME_VENDOR_PATH_PARITY_PASS" if matched else "STAGING_SAME_VENDOR_PATH_PARITY_MISMATCH",
        "expected_completed_session": expected_session,
        "vendor_rows": len(v_dates),
        "reference_rows": len(r_dates),
        "calendar_equal": calendars_match,
        "first_date_vendor": v_dates[0],
        "first_date_reference": r_dates[0],
        "last_date": expected_session,
        "mismatch_count": len(differences) if calendars_match else None,
        "first_mismatches": differences[:4],
        "vendor_feature_sha256": vendor_sha,
        "reference_feature_sha256": ref_sha,
        "feature_fingerprints_equal": vendor_sha == ref_sha,
        "broker_actions": False,
        "market_data_written": False,
        "second_provider_proven": False,
        "provider": "YAHOO_CHART_VS_YFINANCE_YAHOO_AUTO_ADJUST",
    }
    if matched:
        # Replaying the original frozen implementation from both price arrays
        # verifies actual decisions, not just equality of a few final prices.
        original = build_signal(
            vendor_raw, now, source="YAHOO_CHART", source_sha256="0"*64
        )
        ref_buffer = io.StringIO(newline="")
        writer = csv.writer(ref_buffer, lineterminator="\n")
        writer.writerow(["Date", "Close"])
        writer.writerows(zip(r_dates, (format(x, ".17g") for x in r_closes)))
        frozen = build_signal(
            ref_buffer.getvalue().encode("utf-8"), now,
            source="YFINANCE_AUTO_ADJUST", source_sha256="1"*64
        )
        semantic_keys = ("latest", "previous", "action", "execution_plan")
        result["decisions_equal"] = all(
            original[k] == frozen[k] for k in semantic_keys
        )
        if not result["decisions_equal"]:
            result["status"] = "STAGING_SAME_VENDOR_PATH_PARITY_MISMATCH"
    else:
        result["decisions_equal"] = False
    return result


def compare_live_paths(*, now: datetime, chart_fetch=None, reference_fetch=None) -> dict:
    """Read-only Yahoo chart + frozen yfinance data path comparison."""
    if now.tzinfo is None:
        raise ValueError("SOURCE_PARITY_REQUIRES_AWARE_CLOCK")
    chart, vendor_sha = (chart_fetch or _vendor_request)(now=now)
    trimmed, removed, raw_last = _completed_chart(chart, now=now)
    expected = completed_xnys_session(now)
    vendor_csv, _ = extract_adjusted_qqq(
        trimmed, now=now, expected_session=expected
    )
    if reference_fetch is None:
        from stocklens.data import load_qqq_history
        frame, reference_audit = load_qqq_history(now_ny=now.astimezone(NY))
    else:
        frame, reference_audit = reference_fetch(now=now)
    result = compare_completed_histories(
        vendor_raw=vendor_csv, reference_df=frame,
        expected_session=expected, now=now
    )
    result["vendor_raw_response_sha256"] = vendor_sha
    result["vendor_raw_last_date"] = raw_last
    result["dropped_incomplete_vendor_current_session"] = removed
    result["reference_dropped_incomplete_current_session"] = bool(
        reference_audit.get("dropped_incomplete_current_session")
    )
    return result

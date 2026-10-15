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
from stocklens.core import replay_levels

MINIMUM_EXPECTED_DAYS = 300

# A diagnostic budget defined in terms of IEEE-754 binary32 precision,
# not a hand-picked price delta. The observed 2008 example is ~3 binary32
# ULPs (a few millionths of a dollar). This does NOT explain its origin.
MAX_BINARY32_ULPS = 8


def _binary32_ulp(value: float) -> float:
    """Spacing around a positive normal IEEE binary32 value, no NumPy needed."""
    if not math.isfinite(value) or value <= 0:
        raise ValueError("INVALID_BINARY32_REFERENCE_VALUE")
    exponent = math.frexp(value)[1] - 1
    return math.ldexp(1.0, max(exponent - 23, -149))


def _policy_state(decision) -> tuple:
    """Only actual frozen trading policy, not raw floating-point features."""
    return (
        decision.asof_date, decision.level, decision.defense_active,
        decision.target_leverage, decision.qqq_weight, decision.tqqq_weight,
        decision.invested_fraction,
    )


def _next_action(previous, latest) -> str:
    """Same action convention as frozen stocklens.shadow, without mutation."""
    action = "NO_CHANGE"
    if previous is None or previous.target_leverage != latest.target_leverage:
        action = "REBALANCE_NEXT_SESSION"
    if previous is not None and previous.defense_active != latest.defense_active:
        action = (
            "ENTER_CASH_NEXT_SESSION" if latest.defense_active
            else "EXIT_CASH_NEXT_SESSION"
        )
    return action


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
    feature_fingerprints_equal = vendor_sha == ref_sha

    # Exact-to-1e-8 comparison is retained as a *diagnostic* rather than
    # treated as proof of different executable decisions. The non-exact
    # bucket uses a binary32 ULP-based bound, never a whole-cent tolerance.
    exact_price_differences = []
    outside_binary32_budget = []
    largest_binary32_ulp_distance = 0.0
    max_abs_price_difference = 0.0
    max_rel_price_difference = 0.0
    rounding_compatible_count = 0
    nonidentical_price_count = 0
    price_examples = []
    if calendars_match:
        for day, vendor, reference in zip(v_dates, v_closes, r_closes):
            difference = abs(vendor - reference)
            ulp = max(_binary32_ulp(vendor), _binary32_ulp(reference))
            ulp_distance = difference / ulp
            relative = difference / max(vendor, reference)
            largest_binary32_ulp_distance = max(
                largest_binary32_ulp_distance, ulp_distance
            )
            max_abs_price_difference = max(max_abs_price_difference, difference)
            max_rel_price_difference = max(max_rel_price_difference, relative)
            if difference > 0:
                nonidentical_price_count += 1
            if not math.isclose(vendor, reference, abs_tol=1e-8, rel_tol=1e-8):
                exact_price_differences.append((day, round(vendor, 8), round(reference, 8)))
            if difference > MAX_BINARY32_ULPS * ulp:
                outside_binary32_budget.append(
                    {"date": day, "chart": vendor, "yfinance": reference,
                     "abs_difference": difference, "binary32_ulp_distance": ulp_distance}
                )
            elif difference > 0:
                rounding_compatible_count += 1
            if difference > 0 and len(price_examples) < 4:
                price_examples.append(
                    {"date": day, "chart": vendor, "yfinance": reference,
                     "binary32_ulp_distance": round(ulp_distance, 4)}
                )

    # Crucial: independently replay *every* trading day since 2009-09-01
    # even when prices differ, so a branch flip is never hidden by a numeric
    # tolerance or by an equal latest 253-session fingerprint.
    decisions_checked = calendars_match
    policy_disagreements = []
    decision_count = 0
    latest_policy_equal = False
    latest_action_equal = False
    feature_differences = None
    if decisions_checked:
        vendor_decisions = replay_levels(v_closes, v_dates)
        reference_decisions = replay_levels(r_closes, r_dates)
        if len(vendor_decisions) != len(reference_decisions):
            raise RuntimeError("FROZEN_REPLAY_LENGTH_DIVERGENCE")
        decision_count = len(vendor_decisions)
        for first, second in zip(vendor_decisions, reference_decisions):
            a = _policy_state(first)
            b = _policy_state(second)
            if a != b:
                policy_disagreements.append(
                    {"date": first.asof_date, "chart": list(a),
                     "yfinance": list(b)}
                )
        latest_policy_equal = (
            _policy_state(vendor_decisions[-1])
            == _policy_state(reference_decisions[-1])
        )
        latest_action_equal = (
            _next_action(vendor_decisions[-2], vendor_decisions[-1])
            == _next_action(reference_decisions[-2], reference_decisions[-1])
        )
        a = vendor_decisions[-1].features
        b = reference_decisions[-1].features
        feature_differences = {
            k: abs(getattr(a, k) - getattr(b, k))
            for k in ("close", "sma50", "sma200", "vol20", "mom12")
        }
    decisions_equal = (
        decisions_checked and not policy_disagreements
        and latest_policy_equal and latest_action_equal
    )
    numeric_rounding_compatible = (
        calendars_match and not outside_binary32_budget
    )
    accepted = (
        numeric_rounding_compatible
        and feature_fingerprints_equal
        and decisions_equal
    )
    price_classification = (
        "IDENTICAL_AT_1E-8"
        if calendars_match and not exact_price_differences
        else "WITHIN_8_BINARY32_ULPS"
        if numeric_rounding_compatible
        else "OUTSIDE_8_BINARY32_ULPS_OR_DATE_MISMATCH"
    )
    return {
        "status": (
            "STAGING_SAME_VENDOR_PATH_PARITY_PASS" if accepted
            else "STAGING_SAME_VENDOR_PATH_PARITY_MISMATCH"
        ),
        "expected_completed_session": expected_session,
        "vendor_rows": len(v_dates),
        "reference_rows": len(r_dates),
        "calendar_equal": calendars_match,
        "first_date_vendor": v_dates[0],
        "first_date_reference": r_dates[0],
        "last_date": expected_session,
        "mismatch_count": len(exact_price_differences) if calendars_match else None,
        "first_mismatches": exact_price_differences[:4],
        "nonidentical_price_count": nonidentical_price_count if calendars_match else None,
        "rounding_compatible_price_count": rounding_compatible_count if calendars_match else None,
        "outside_binary32_precision_count": len(outside_binary32_budget) if calendars_match else None,
        "first_outside_precision_budget": outside_binary32_budget[:5],
        "max_binary32_ulp_distance": largest_binary32_ulp_distance if calendars_match else None,
        "max_absolute_price_difference": max_abs_price_difference if calendars_match else None,
        "max_relative_price_difference": max_rel_price_difference if calendars_match else None,
        "first_nonidentical_price_examples": price_examples,
        "price_precision_classification": price_classification,
        "binary32_ulp_limit": MAX_BINARY32_ULPS,
        "numeric_rounding_compatible": numeric_rounding_compatible,
        "vendor_feature_sha256": vendor_sha,
        "reference_feature_sha256": ref_sha,
        "feature_fingerprints_equal": feature_fingerprints_equal,
        "decision_check_executed": decisions_checked,
        "decisions_compared_count": decision_count,
        "policy_mismatch_count": len(policy_disagreements) if decisions_checked else None,
        "first_policy_mismatches": policy_disagreements[:5],
        "latest_policy_equal": latest_policy_equal if decisions_checked else None,
        "latest_action_equal": latest_action_equal if decisions_checked else None,
        "latest_feature_absolute_differences": feature_differences,
        "decisions_equal": decisions_equal,
        "broker_actions": False,
        "market_data_written": False,
        "second_provider_proven": False,
        "price_rounding_origin_proven": False,
        "provider": "YAHOO_CHART_VS_YFINANCE_YAHOO_AUTO_ADJUST",
    }

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

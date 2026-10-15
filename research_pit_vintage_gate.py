"""Fail-closed OFFLINE FRED/ALFRED as-of snapshot shape audit. Not PIT first-seen certification."""
from datetime import date
from hashlib import sha256
import json
import math

BOUNDS = {"T10Y3M": (-30., 30.), "BAMLH0A0HYM2": (0., 100.)}

def day(x):
    if not isinstance(x, str):
        raise ValueError("noncanonical date")
    try:
        d = date.fromisoformat(x)
    except ValueError as e:
        raise ValueError("noncanonical date") from e
    if d.isoformat() != x:
        raise ValueError("noncanonical date")
    return d

def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result

def reject_constant(value):
    raise ValueError("nonfinite JSON constant")

def audit_snapshot(raw: bytes, *, trade_date: str, expected_series: str) -> dict:
    if expected_series not in BOUNDS:
        raise ValueError("unregistered series")
    if not isinstance(raw, bytes) or not 0 < len(raw) <= 8_000_000:
        raise ValueError("invalid raw envelope")
    trade = day(trade_date)
    try:
        env = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_pairs,
                         parse_constant=reject_constant)
    except (UnicodeError, ValueError) as e:
        raise ValueError("invalid raw JSON") from e
    if not isinstance(env, dict) or env.get("series_id") != expected_series:
        raise ValueError("wrong pinned series")
    response = env.get("response")
    if not isinstance(response, dict):
        raise ValueError("missing native response")
    if (response.get("units") != "lin" or type(response.get("output_type")) is not int
            or response["output_type"] != 1):
        raise ValueError("transformed or multi-vintage output")
    if response.get("file_type") != "json":
        raise ValueError("not original JSON output")
    if response.get("order_by") != "observation_date" or response.get("sort_order") != "asc":
        raise ValueError("unexpected observation ordering")
    asof = day(response.get("realtime_start"))
    if day(response.get("realtime_end")) != asof or asof >= trade:
        raise ValueError("future or multi-day as-of window")
    start, end = day(response.get("observation_start")), day(response.get("observation_end"))
    if start > end:
        raise ValueError("invalid observation range")
    rows = response.get("observations")
    if (not isinstance(rows, list) or not rows or type(response.get("count")) is not int
            or type(response.get("offset")) is not int or response["offset"] != 0
            or response["count"] != len(rows) or type(response.get("limit")) is not int
            or response["limit"] < len(rows)):
        raise ValueError("incomplete or paginated response")
    previous = None
    missing = 0
    old = 0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("invalid observation")
        observed = day(row.get("date"))
        if observed < start or observed > end or observed > asof:
            raise ValueError("future or out-of-range observation")
        if previous is not None and observed <= previous:
            raise ValueError("duplicate or unsorted observations")
        previous = observed
        if not day(row.get("realtime_start")) <= asof <= day(row.get("realtime_end")):
            raise ValueError("observation not valid in as-of window")
        old += int(observed.year <= 2022)
        value = row.get("value")
        if value == ".":
            missing += 1
            continue
        if type(value) not in (str, int, float):
            raise ValueError("invalid series value")
        try:
            number = float(value)
        except (ValueError, OverflowError) as e:
            raise ValueError("invalid series value") from e
        low, high = BOUNDS[expected_series]
        if not math.isfinite(number) or not low <= number <= high:
            raise ValueError("invalid series value")
    return {
        "kind": "FRED_ALFRED_ASOF_SNAPSHOT_SHAPE_AUDIT",
        "series_id": expected_series, "asof_date": asof.isoformat(),
        "trade_date": trade.isoformat(), "raw_envelope_sha256": sha256(raw).hexdigest(),
        "rows": len(rows), "nonmissing_rows": len(rows)-missing, "missing_rows": missing,
        "pre2023_observation_rows_not_first_seen_proof": old,
        "historical_first_seen_independently_certified": False,
        "intraday_publication_time_verified": False,
        "ice_redistribution_permission_verified": False,
        "economically_qualified_rows": 0,
        "status": "BLOCKED_SOURCE_CLOCK_LICENSE_AND_EXTERNAL_RECEIPT",
        "historical_sample_reused": True, "broker_orders_authorized": False,
        "automatic_promotion": False, "frozen_stocklens8_changed": False,
    }

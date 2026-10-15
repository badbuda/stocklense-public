"""Yahoo Finance observed adjusted daily QQQ ingestion for the staged AWS pipeline.

Only the public vendor market-data endpoint is contacted. No GitHub reads,
no derived/synthetic TQQQ, no broker operations. The raw vendor response
is still unverified by a second provider; manifests explicitly say so.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import urllib.parse
import urllib.request
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
YAHOO_HOST = "query1.finance.yahoo.com"
START_TS = int(datetime(2008, 1, 1, tzinfo=timezone.utc).timestamp())
MAX_RESPONSE_BYTES = 3_000_000


class MarketDataError(RuntimeError):
    pass


def _vendor_request(*, now: datetime, urlopen=urllib.request.urlopen):
    if now.tzinfo is None:
        raise MarketDataError("NAIVE_CLOCK")
    params = urllib.parse.urlencode({
        "period1": START_TS,
        "period2": int(now.timestamp()) + 86400,
        "interval": "1d",
        "events": "div,splits",
    })
    url = "https://" + YAHOO_HOST + "/v8/finance/chart/QQQ?" + params
    request = urllib.request.Request(
        url, headers={"User-Agent": "Mozilla/5.0 StockLens-Shadow/8.0"}
    )
    with urlopen(request, timeout=20) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise MarketDataError("VENDOR_RESPONSE_TOO_LARGE")
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def extract_adjusted_qqq(payload: dict, *, now: datetime,
                         expected_session: str) -> tuple[bytes, dict]:
    """Require actual chart adjclose data and an exact completed session.

    The chart endpoint returns adjusted daily closes also used by yfinance.
    Reconcile numeric outputs against frozen yfinance on identical dates
    before production activation; this function does not certify parity.
    """
    if now.tzinfo is None:
        raise MarketDataError("NAIVE_CLOCK")
    ny = now.astimezone(NY)
    try:
        expected = date.fromisoformat(expected_session)
    except (ValueError, TypeError) as exc:
        raise MarketDataError("INVALID_EXPECTED_SESSION") from exc
    if expected.isoformat() != expected_session:
        raise MarketDataError("NONCANONICAL_EXPECTED_SESSION")
    if expected > ny.date() or (expected == ny.date() and ny.time() < time(18, 0)):
        raise MarketDataError("SESSION_NOT_COMPLETED")
    if (ny.date() - expected).days > 5:
        raise MarketDataError("STALE_EXPECTED_SESSION")

    try:
        chart = payload["chart"]
        if chart.get("error") is not None:
            raise MarketDataError("VENDOR_CHART_ERROR")
        series = chart["result"][0]
        timestamps = series["timestamp"]
        prices = series["indicators"]["adjclose"][0]["adjclose"]
        metadata = series["meta"]
    except (KeyError, IndexError, TypeError) as exc:
        raise MarketDataError("MISSING_VENDOR_ADJUSTED_CLOSE") from exc
    if metadata.get("symbol") != "QQQ":
        raise MarketDataError("WRONG_VENDOR_SYMBOL")
    if metadata.get("exchangeTimezoneName") != "America/New_York":
        raise MarketDataError("WRONG_VENDOR_TIMEZONE")
    if len(timestamps) != len(prices) or len(prices) < 300:
        raise MarketDataError("INVALID_VENDOR_HISTORY_SIZE")

    rows = []
    last_day = None
    for stamp, price in zip(timestamps, prices):
        if stamp is None or price is None:
            # A null past adjusted close is not silently removed.
            raise MarketDataError("MISSING_VENDOR_PRICE")
        try:
            current_day = datetime.fromtimestamp(int(stamp), NY).date()
            numeric = float(price)
        except (ValueError, TypeError, OverflowError) as exc:
            raise MarketDataError("INVALID_VENDOR_PRICE") from exc
        if not math.isfinite(numeric) or numeric <= 0:
            raise MarketDataError("INVALID_VENDOR_PRICE")
        if last_day is not None and current_day <= last_day:
            raise MarketDataError("VENDOR_DATE_NOT_STRICTLY_INCREASING")
        if (expected - current_day).days < 0:
            # Yahoo may publish a partial bar for today: reject/fail closed
            # rather than silently drop a vendor-provided row.
            raise MarketDataError("UNEXPECTED_FUTURE_OR_PARTIAL_BAR")
        rows.append((current_day.isoformat(), numeric))
        last_day = current_day
    if rows[0][0] > "2008-01-10":
        raise MarketDataError("INSUFFICIENT_PRE2009_WARMUP")
    if rows[-1][0] != expected_session:
        raise MarketDataError("LAST_VENDOR_SESSION_MISMATCH")
    # Historical weekends indicate a timestamp/market-source mapping problem.
    if any(date.fromisoformat(d).weekday() > 4 for d, _ in rows):
        raise MarketDataError("WEEKEND_VENDOR_BAR")

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow(["Date", "Close"])
    writer.writerows((d, format(price, ".17g")) for d, price in rows)
    csv_bytes = output.getvalue().encode("utf-8")
    audit = {
        "provider": "YAHOO_CHART_PUBLIC_ENDPOINT",
        "symbol": "QQQ",
        "data_type": "QQQ_ADJUSTED_DAILY",
        "price_field": "indicators.adjclose[0].adjclose",
        "exchange_timezone": "America/New_York",
        "retrieved_at_utc": now.astimezone(timezone.utc).isoformat(),
        "first_session": rows[0][0],
        "last_session": rows[-1][0],
        "row_count": len(rows),
        "csv_sha256": hashlib.sha256(csv_bytes).hexdigest(),
        "validation_scope": "SCHEMA_SESSION_CHECKS_ONLY_NO_INDEPENDENT_VENDOR_PARITY",
    }
    return csv_bytes, audit


def ingest(expected_session: str, *, now: datetime | None = None,
           urlopen=urllib.request.urlopen):
    now = now or datetime.now(timezone.utc)
    payload, vendor_sha256 = _vendor_request(now=now, urlopen=urlopen)
    raw, audit = extract_adjusted_qqq(payload, now=now, expected_session=expected_session)
    audit["vendor_response_sha256"] = vendor_sha256
    return raw, audit

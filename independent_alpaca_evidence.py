"""Fetch strictly read-only adjusted QQQ daily bars from an INDEPENDENT vendor.

Alpaca Market Data only: never Trading API, broker, order, DynamoDB or S3.
Uses operator-set environment credentials; never prints or persists secrets.
Output CSV is evidence input for independent_vendor_parity.py in staging PR #78,
NOT proof of executable fills, source-as-of consistency, or production readiness.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo

DATA_URL = "https://data.alpaca.markets/v2/stocks/QQQ/bars"
NY = ZoneInfo("America/New_York")
MAX_PAGES = 20


def fetch_page(params: dict, *, key: str, secret: str) -> dict:
    url = DATA_URL + "?" + urlencode(params)
    req = Request(url, headers={
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
    })
    try:
        with urlopen(req, timeout=30) as response:
            content = response.read(6_000_001)
        if len(content) > 6_000_000:
            raise ValueError("ALPACA_PAGE_OVERSIZE")
        data = json.loads(content)
    except HTTPError as error:
        raise RuntimeError("ALPACA_MARKET_DATA_HTTP_" + str(error.code)) from None
    except URLError:
        raise RuntimeError("ALPACA_MARKET_DATA_CONNECTION_FAILED") from None
    if not isinstance(data, dict):
        raise ValueError("ALPACA_NONOBJECT_PAGE")
    return data


def collect(*, session: str, feed: str, load_page) -> tuple[bytes, dict]:
    if date.fromisoformat(session).isoformat() != session:
        raise ValueError("INVALID_COMPLETED_SESSION")
    if feed not in ("sip", "iex"):
        raise ValueError("ALPACA_EXPLICIT_FEED_REQUIRED")
    start = date(2008, 1, 1)
    end = date.fromisoformat(session) + timedelta(days=1)
    params = {
        "timeframe": "1Day", "start": start.isoformat(),
        "end": end.isoformat(), "adjustment": "all",
        "feed": feed, "limit": 10000,
    }
    prices: dict[str, float] = {}
    seen_tokens: set[str] = set()
    page_count = 0
    while True:
        page_count += 1
        if page_count > MAX_PAGES:
            raise RuntimeError("ALPACA_PAGINATION_EXCEEDED")
        page = load_page(dict(params))
        bars = page.get("bars")
        if not isinstance(bars, list):
            raise ValueError("ALPACA_NOT_HISTORICAL_DAILY_BARS")
        for bar in bars:
            if not isinstance(bar, dict) or not isinstance(bar.get("t"), str):
                raise ValueError("ALPACA_INVALID_DAILY_BAR")
            at = datetime.fromisoformat(bar["t"].replace("Z", "+00:00"))
            if at.tzinfo is None:
                raise ValueError("ALPACA_NAIVE_MARKET_TIMESTAMP")
            day = at.astimezone(NY).date().isoformat()
            value = bar.get("c")
            if isinstance(value, bool) or not isinstance(value, (int,float)) or (
                not math.isfinite(float(value)) or value <= 0
            ):
                raise ValueError("ALPACA_INVALID_ADJUSTED_CLOSE")
            if day in prices:
                raise ValueError("ALPACA_DUPLICATE_SESSION")
            if day > session:
                raise ValueError("ALPACA_FUTURE_OR_INCOMPLETE_SESSION")
            prices[day] = float(value)
        token = page.get("next_page_token")
        if not token:
            break
        if not isinstance(token, str) or token in seen_tokens:
            raise ValueError("ALPACA_INVALID_PAGINATION")
        seen_tokens.add(token)
        params["page_token"] = token

    days = sorted(prices)
    if len(days) < 300 or not days or days[-1] != session:
        raise ValueError("ALPACA_HISTORY_INCOMPLETE_LAST_SESSION")
    if days[0] > "2008-01-10" or sum(d < "2009-09-01" for d in days) < 252:
        raise ValueError("ALPACA_FROZEN_WARMUP_INSUFFICIENT")
    if len(days) != len(set(days)):
        raise ValueError("ALPACA_DUPLICATE_MARKET_DATE")
    # The matching XNYS calendar and per-day policy are verified by the
    # separate read-only frozen-vs-independent source comparator. Never patch
    # missing bars, interpolate or synthesize historic market data here.
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(["Date","Close"])
    for day in days:
        writer.writerow([day,format(prices[day],".17g")])
    data = out.getvalue().encode("utf-8")
    return data, {
        "status": "ALPACA_INDEPENDENT_DAILY_CSV_DOWNLOADED_NOT_YET_RECONCILED",
        "provider": "ALPACA_MARKET_DATA", "symbol": "QQQ",
        "feed": feed, "adjustment": "all", "first_session": days[0],
        "last_session": days[-1], "session_count": len(days),
        "page_count": page_count, "csv_sha256": hashlib.sha256(data).hexdigest(),
        "full_policy_parity_verified": False, "broker_actions": False,
        "cutover_authorized": False,
    }


def main() -> None:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--session", required=True)
    cli.add_argument("--feed", choices=["sip","iex"], default="sip")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args()
    key = os.environ.get("ALPACA_DATA_KEY")
    secret = os.environ.get("ALPACA_DATA_SECRET")
    if not key or not secret:
        raise SystemExit("MISSING_ALPACA_MARKET_DATA_CREDENTIALS_USE_ENV_NOT_CLI")
    result, report = collect(
        session=args.session, feed=args.feed,
        load_page=lambda params: fetch_page(params,key=key,secret=secret)
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # No symlink following / accidental overwrite of existing immutable evidence.
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"): flags |= os.O_NOFOLLOW
    descriptor = os.open(args.output, flags, 0o600)
    with os.fdopen(descriptor,"wb") as handle:
        handle.write(result)
    print(json.dumps({**report,"output":str(args.output)},sort_keys=True))


if __name__ == "__main__":
    main()

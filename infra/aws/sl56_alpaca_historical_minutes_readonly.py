#!/usr/bin/env python3
"""Read-only research probe for honest 1-minute QQQ/TQQQ Nov5/6 gap recovery.

Requires user-supplied Alpaca historical-data API credentials via environment.
No AWS account access; no S3 writes; no brokers; never creates Paper receipts.
Historical SIP access and completeness are NOT assumed until verified from
the actual authenticated API response and each XNYS minute timestamp.
"""
from __future__ import annotations

import argparse
from datetime import date, timezone
import json
import os
import sys
import urllib.parse
import urllib.request
from urllib.error import HTTPError, URLError

from stocklens.paper_minute_coverage import audit_pair

HOST = "https://data.alpaca.markets/v2/stocks/bars"
SYMBOLS = ("QQQ", "TQQQ")


def fetch_symbol(symbol, session, *, key, secret, opener=None):
    """GET-only SIP 1m historical; paginate and reject incomplete API replies."""
    if symbol not in SYMBOLS:
        raise ValueError("UNEXPECTED_MARKET_SYMBOL")
    first = date.fromisoformat(session)
    if first.isoformat() != session:
        raise ValueError("NON_CANONICAL_SESSION")
    # Calendar session UTC boundaries, not naive US daylight guesses.
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS")
    if not cal.is_session(session):
        raise ValueError("NON_XNYS_SESSION")
    start = cal.session_open(session).to_pydatetime().astimezone(timezone.utc)
    end = cal.session_close(session).to_pydatetime().astimezone(timezone.utc)
    query = {
        "symbols": symbol, "timeframe": "1Min", "feed": "sip",
        "adjustment": "raw", "start": start.isoformat(),
        "end": end.isoformat(), "limit": 1000, "sort": "asc",
    }
    result = []
    seen_tokens = set()
    for _ in range(15):
        url = HOST + "?" + urllib.parse.urlencode(query)
        request = urllib.request.Request(url, headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
            "User-Agent": "stocklens-sl56-research-readonly",
        }, method="GET")
        try:
            with (opener or urllib.request.urlopen)(request, timeout=35) as response:
                payload = response.read(3_000_001)
        except HTTPError as exc:
            # Do not log any credential, response body, or signed request.
            raise RuntimeError("ALPACA_SIP_HTTP_STATUS:" + str(exc.code)) from None
        except URLError as exc:
            raise RuntimeError("ALPACA_NETWORK_READ_FAILED:" + type(exc).__name__) from None
        if len(payload) > 3_000_000:
            raise RuntimeError("ALPACA_SIP_RESPONSE_TOO_BIG")
        data = json.loads(payload)
        if data.get("error") or not isinstance(data.get("bars"), dict):
            raise RuntimeError("ALPACA_SIP_RESPONSE_NOT_BARS")
        batch = data["bars"]
        if set(batch) - {symbol} or not isinstance(batch.get(symbol), list):
            raise RuntimeError("ALPACA_SIP_SYMBOL_OR_BARS_INVALID")
        result.extend(batch[symbol])
        next_token = data.get("next_page_token")
        if not next_token:
            return result
        if not isinstance(next_token, str) or next_token in seen_tokens:
            raise RuntimeError("ALPACA_PAGINATION_CYCLE")
        seen_tokens.add(next_token)
        query["page_token"] = next_token
    raise RuntimeError("ALPACA_PAGINATION_UNFINISHED")


def main(argv=None):
    p = argparse.ArgumentParser(description="No broker, no S3, no Paper writes")
    p.add_argument("--session", choices=("2026-11-05", "2026-11-06"),
                   default="2026-11-05")
    args = p.parse_args(argv)
    key = os.environ.get("APCA_API_KEY_ID") or os.environ.get("ALPACA_API_KEY_ID")
    secret = os.environ.get("APCA_API_SECRET_KEY") or os.environ.get("ALPACA_API_SECRET_KEY")
    if not key or not secret:
        print(json.dumps({
            "status": "ALPACA_HISTORICAL_READONLY_CREDENTIALS_REQUIRED",
            "no_fallback": True, "aws_mutations": False,
            "broker_orders": False, "paper_backfill": False,
        }))
        return 2
    try:
        observed = {s: fetch_symbol(s, args.session, key=key, secret=secret)
                    for s in SYMBOLS}
        answer = audit_pair(observed, args.session)
        print(json.dumps(answer, sort_keys=True))
        return 0 if answer["status"] == "RESEARCH_PAIR_COMPLETE_NOT_EXECUTION_AUTHORIZATION" else 2
    except Exception as exc:
        print(json.dumps({
            "status": "RESEARCH_PROVIDER_OR_BAR_VALIDATION_BLOCKED",
            "reason": str(exc)[:160],
            "aws_mutations": False,
            "broker_orders": False,
            "paper_backfill": False,
        }))
        return 2


if __name__ == "__main__":
    sys.exit(main())

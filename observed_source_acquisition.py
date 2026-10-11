"""Optional, bounded acquisition of *observed* GLD/TLT and NY Fed EFFR.

Research only. Not a first-seen or broker interest audit. Data is kept in a
private, non-committed folder and emitted as short-retention CI artifacts.
No strategy code or broker access. Missing prices FAIL CLOSED; no synthetic ETF.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path
import hashlib
import json
import math
import os
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from observed_etf_two_question_audit import load
from research_diversified_sleeve_contract import inspect as inspect_sleeve

OUT = Path("research/private")
SUMMARY = Path("research/results/observed_external_data_intake.json")
GLD = "https://finance.yahoo.com/quote/GLD/history/"
TLT = "https://finance.yahoo.com/quote/TLT/history/"
EFFR_ENDPOINT = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json"
SYMBOLS = ("GLD", "TLT")


def normalize_prices(frame, symbol, requested_dates):
    """Rows are never interpolated, forward-filled, or backdated."""
    import pandas as pd
    if symbol not in SYMBOLS:
        raise ValueError("EXTERNAL_UNAPPROVED_SYMBOL")
    if frame is None or frame.empty:
        raise ValueError("EXTERNAL_EMPTY_PRICE_SOURCE")
    if isinstance(frame.columns, pd.MultiIndex):
        try:
            opens = frame["Open"][symbol]
            closes = frame["Close"][symbol]
        except KeyError as exc:
            raise ValueError("EXTERNAL_OHLC_COLUMNS_MISSING") from exc
    else:
        if "Open" not in frame or "Close" not in frame:
            raise ValueError("EXTERNAL_OHLC_COLUMNS_MISSING")
        opens, closes = frame["Open"], frame["Close"]
    dates = [pd.Timestamp(t).date().isoformat() for t in frame.index]
    if dates != sorted(set(dates)):
        raise ValueError("EXTERNAL_DUPLICATE_OR_UNSORTED_SESSIONS")
    observed = {}
    for i, d in enumerate(dates):
        o, c = opens.iloc[i], closes.iloc[i]
        if (not isinstance(o, (int, float)) and not hasattr(o, "__float__")) or (
            not isinstance(c, (int, float)) and not hasattr(c, "__float__")
        ):
            raise ValueError("EXTERNAL_INVALID_OBSERVED_BAR")
        try:
            o, c = float(o), float(c)
        except (TypeError, ValueError) as exc:
            raise ValueError("EXTERNAL_INVALID_OBSERVED_BAR") from exc
        if not (math.isfinite(o) and math.isfinite(c) and o > 0 and c > 0):
            raise ValueError("EXTERNAL_INVALID_OBSERVED_BAR")
        observed[d] = {"date": d, "open": o, "close": c}
    missing = sorted(set(requested_dates).difference(observed))
    if missing:
        raise ValueError("EXTERNAL_MISSING_REAL_OBSERVED_SESSIONS:" +
                         str(len(missing)) + ":" + ",".join(missing[:4]))
    return [observed[d] for d in requested_dates]


def download_external_prices(symbol, requested_dates):
    import yfinance as yf
    if symbol not in SYMBOLS:
        raise ValueError("EXTERNAL_UNAPPROVED_SYMBOL")
    start = requested_dates[0]
    end = (date.fromisoformat(requested_dates[-1]) + timedelta(days=1)).isoformat()
    frame = yf.download(symbol, start=start, end=end, interval="1d",
                        auto_adjust=True, actions=False, progress=False,
                        threads=False)
    return normalize_prices(frame, symbol, requested_dates)


def normalize_effr_payload(payload, first_date, last_date):
    """Only raw NY Fed effective-day rates. Do NOT invent published-at times."""
    if not isinstance(payload, dict):
        raise ValueError("EFFR_NOT_JSON_OBJECT")
    rows = payload.get("refRates")
    if not isinstance(rows, list) or not rows:
        raise ValueError("EFFR_API_SCHEMA_UNRECOGNIZED")
    accepted = {}
    for item in rows:
        if not isinstance(item, dict):
            raise ValueError("EFFR_MALFORMED_ROW")
        d = item.get("effectiveDate")
        percent = item.get("percentRate")
        if not isinstance(d, str) or type(percent) not in (str, float, int):
            raise ValueError("EFFR_MISSING_EFFECTIVE_RATE")
        try:
            effective = date.fromisoformat(d)
            rate = float(percent)
        except ValueError as exc:
            raise ValueError("EFFR_INVALID_VALUE") from exc
        if not math.isfinite(rate) or not 0 <= rate <= 25:
            raise ValueError("EFFR_INVALID_PERCENT_RATE")
        if first_date <= effective.isoformat() <= last_date:
            if d in accepted and accepted[d] != rate:
                raise ValueError("EFFR_MULTIPLE_VINTAGES_WITHOUT_PIT_REVISION")
            accepted[d] = rate
    if not accepted:
        raise ValueError("EFFR_NO_MATCHING_EFFECTIVE_DATES")
    return [{"effective_date": d, "rate_percent": accepted[d],
             "provider_publication_timestamp_verified": False}
            for d in sorted(accepted)]


def download_effr(first_date, last_date):
    args = urlencode({"startDate": first_date, "endDate": last_date})
    url = EFFR_ENDPOINT + "?" + args
    req = Request(url, headers={"Accept": "application/json",
                                "User-Agent": "StockLens research-readonly/1.0"})
    with urlopen(req, timeout=25) as rsp:
        body = rsp.read(12 * 1024 * 1024 + 1)
    if len(body) > 12 * 1024 * 1024:
        raise ValueError("EFFR_SOURCE_RESPONSE_TOO_LARGE")
    return normalize_effr_payload(json.loads(body), first_date, last_date), url


def run():
    market = load()
    dates = [x["date"] for x in market["daily"]]
    OUT.mkdir(parents=True, exist_ok=True)
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    status = {"schema_version": 1, "kind": "SL9_012_EXTERNAL_OBSERVED_DATA_INTAKE",
              "baseline_market_sessions": len(dates),
              "baseline_snapshot_sha256": market.get("snapshot_sha256"),
              "frozen_stocklens8_changed": False,
              "synthetic_etf_prices_used": False,
              "independently_certified_source": False,
              "historical_provider_first_seen_proven": False,
              "broker_cash_rate_proven": False,
              "strategy_returns_computed": False,
              "automatic_promotion": False,
              "capital_deployment_authorized": False,
              "symbols": {}, "effr": {}}
    bars = {}
    for symbol in SYMBOLS:
        try:
            series = download_external_prices(symbol, dates)
            bars[symbol] = series
            status["symbols"][symbol] = {"status": "OBSERVED_SOURCE_COMPLETE_UNAUDITED",
                "sessions": len(series),
                "start": series[0]["date"], "end": series[-1]["date"]}
        except (ValueError, RuntimeError, OSError, KeyError, IndexError) as exc:
            status["symbols"][symbol] = {"status": "BLOCKED_SOURCE_MISSING_OR_INVALID",
                                          "reason": str(exc)[:160]}
    if set(bars) == set(SYMBOLS):
        source = {"schema_version": 1,
                  "price_basis": "OBSERVED_ADJUSTED_DAILY_OPEN_CLOSE",
                  "source_urls": {"GLD": GLD, "TLT": TLT}, "bars": bars,
                  "source_method": "yfinance.download(auto_adjust=True, interval=1d)",
                  "requested_baseline_snapshot_sha256": market.get("snapshot_sha256"),
                  "provider_first_seen_independently_verified": False}
        validated = inspect_sleeve(market["daily"], source)
        p = OUT / "non_nasdaq_observed_etfs.json"
        p.write_text(json.dumps(source, sort_keys=True, separators=(",", ":")) + "\n")
        status["observed_sleeve_contract"] = validated["status"]
        status["combined_source_data_sha256"] = validated["source_data_sha256"]
    try:
        rows, url = download_effr(dates[0], dates[-1])
        source = {"schema_version": 1, "series": "EFFR",
                  "source_url": url, "observations": rows,
                  "publication_clock_available_in_api": False,
                  "not_broker_deposit_yield": True,
                  "asof_tradability_verified": False}
        p = OUT / "effr_effective_dates_without_publication_clock.json"
        p.write_text(json.dumps(source, sort_keys=True, separators=(",", ":")) + "\n")
        status["effr"] = {"status": "EFFR_EFFECTIVE_DATE_OBSERVED_NOT_PIT_CERTIFIED",
                          "rows": len(rows), "first_effective_date": rows[0]["effective_date"],
                          "last_effective_date": rows[-1]["effective_date"]}
    except (ValueError, RuntimeError, OSError, KeyError, TypeError,
            json.JSONDecodeError) as exc:
        status["effr"] = {"status": "BLOCKED_RATE_SOURCE", "reason": str(exc)[:160]}
    SUMMARY.write_text(json.dumps(status, sort_keys=True, indent=2) + "\n")
    print("STOCKLENS_EXTERNAL_INTAKE=" +
          json.dumps(status, sort_keys=True, separators=(",", ":")))
    return status


if __name__ == "__main__":
    run()

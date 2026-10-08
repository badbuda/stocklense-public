"""Observed ETF minute-price diagnostics, never brokerage fill evidence.

Only Yahoo 1m observed QQQ/TQQQ opening quotes are used. Missing dates/minutes
remain missing, never reconstructed from QQQ synthetic leveraged prices.
This audit does NOT use intraday observations to retune frozen StockLens.
"""
from __future__ import annotations
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
REPORT = "docs/observed_intraday_execution_gap.json"


def evaluate(prices: dict, *, asof_ny: str | None = None) -> dict:
    """Pure, deterministic diagnostic over already observed intraday open prices.

    prices: {symbol: {YYYY-MM-DD: {"09:30": price, "09:31": price,
                                   "09:32": price}}}.
    """
    symbols = ("QQQ", "TQQQ")
    if not all(symbol in prices and isinstance(prices[symbol], dict) for symbol in symbols):
        raise ValueError("OBSERVED_ETF_SYMBOLS_MISSING")
    now = asof_ny or datetime.now(NY).date().isoformat()
    observed = set(prices["QQQ"]) & set(prices["TQQQ"])
    rows = []
    dropped = []
    for d in sorted(set(prices["QQQ"]) | set(prices["TQQQ"])):
        if d >= now:
            dropped.append({"date": d, "reason": "CURRENT_OR_FUTURE_SESSION_UNVERIFIED"})
            continue
        if d not in observed:
            dropped.append({"date": d, "reason": "UNMATCHED_REAL_ETF_SESSION"})
            continue
        row = {"date": d}
        for symbol in symbols:
            src = prices[symbol][d]
            if not all(key in src for key in ("09:30", "09:31", "09:32")):
                dropped.append({"date": d, "reason": "MISSING_OBSERVED_MINUTE:" + symbol})
                break
            p30, p31, p32 = (float(src[t]) for t in ("09:30", "09:31", "09:32"))
            if not all(math.isfinite(x) and x > 0 for x in (p30, p31, p32)):
                dropped.append({"date": d, "reason": "INVALID_OBSERVED_MINUTE:" + symbol})
                break
            row[symbol] = {
                "minute_0930_open": p30,
                "minute_0931_open": p31,
                "minute_0932_open": p32,
                "sell_0931_minus_0930_bps": (p31 / p30 - 1.0) * 10000,
                "buy_0932_minus_0930_bps": (p32 / p30 - 1.0) * 10000,
            }
        else:
            rows.append(row)
    stats = {}
    for symbol in symbols:
        stats[symbol] = {}
        for field in ("sell_0931_minus_0930_bps", "buy_0932_minus_0930_bps"):
            vals = [r[symbol][field] for r in rows]
            stats[symbol][field] = {
                "count": len(vals),
                "mean_bps": sum(vals) / len(vals) if vals else None,
                "worst_absolute_bps": max(map(abs, vals)) if vals else None,
                "min_bps": min(vals) if vals else None,
                "max_bps": max(vals) if vals else None,
            }
    return {
        "schema_version": 1, "kind": "OBSERVED_ETF_INTRADAY_OPEN_TIME_GAP_AUDIT",
        "status": "OBSERVED_SAMPLE_NOT_FILL_PARITY" if rows else "NO_VERIFIED_OBSERVED_SAMPLE",
        "observed_symbols": list(symbols),
        "market_dates": [r["date"] for r in rows],
        "sessions": len(rows), "samples": rows, "excluded": dropped,
        "statistics": stats,
        "price_source": "YFINANCE_1MIN_UNADJUSTED_OBSERVED_OPEN",
        "evidence_scope": "OBSERVED_HISTORICAL_MINUTE_OPEN_PRICES_ONLY",
        "daily_adjusted_open_execution_parity": False,
        "broker_fill_parity": False, "automatic_trading_authorized": False,
        "warning": "This records observed 09:30/09:31/09:32 ETF minute-bar opening prices. "
                   "It is not a broker fill, venue microstructure, transaction quote, adjusted daily-open equality, "
                   "or prospective account P&L. No missing TQQQ quote is synthesized.",
    }


def fetch_minute_prices(days: int = 5) -> dict:
    import yfinance as yf
    from stocklens.paper import _normalize_intraday
    prices = {}
    for symbol in ("QQQ", "TQQQ"):
        raw = yf.download(symbol, period=f"{int(days)}d", interval="1m",
                          auto_adjust=False, actions=False,
                          prepost=False, progress=False, threads=False)
        frame = _normalize_intraday(raw, symbol)
        out = {}
        for row in frame.itertuples():
            ts = row.Index
            hhmm = ts.strftime("%H:%M")
            if hhmm not in ("09:30", "09:31", "09:32"):
                continue
            d = ts.date().isoformat()
            if hhmm in out.setdefault(d, {}):
                raise ValueError("DUPLICATE_MINUTE_PRICE:" + symbol + ":" + d + ":" + hhmm)
            out[d][hhmm] = float(row.Open)
        prices[symbol] = out
    return prices


def build(output=REPORT):
    try:
        observed = fetch_minute_prices()
        report = evaluate(observed)
    except Exception as exc:  # Optional vendor sample: never turn a provider outage into invented prices.
        report = evaluate({"QQQ": {}, "TQQQ": {}})
        report["status"] = "PROVIDER_DATA_UNAVAILABLE"
        report["reason"] = type(exc).__name__
        report["fail_closed"] = True
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "sessions": report["sessions"],
                      "broker_fill_parity": False, "source": report["price_source"]}))
    return report


if __name__ == "__main__":
    build()

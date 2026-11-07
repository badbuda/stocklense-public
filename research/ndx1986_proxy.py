"""1986 Nasdaq-100 index-price research feed; never actual QQQ/TQQQ history.

Uses published FRED NASDAQ100 daily CLOSE values, not ETF opens or total returns.
The frozen 8.0 rules are applied RETROACTIVELY from the first 253-session
warmup; the actual StockLens frozen replay starts in 2009, not 1986.
No broker, trading, tax, or private data access.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
from datetime import date
from pathlib import Path
from urllib.request import Request, urlopen

from stocklens.core import compute_features, next_level, defense_active, LEVEL_LEVERAGE

SOURCE_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQ100"
KIND = "STOCKLENS_NDX_1986_RETROACTIVE_INDEX_RESEARCH_V1"


def parse_fred_csv(payload: bytes) -> list[tuple[str, float]]:
    text = payload.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "NASDAQ100" not in reader.fieldnames:
        raise ValueError("FRED_NASDAQ100_COLUMN_MISSING")
    date_column = "observation_date" if "observation_date" in reader.fieldnames else "DATE"
    if date_column not in reader.fieldnames:
        raise ValueError("FRED_DATE_COLUMN_MISSING")
    rows = []
    for item in reader:
        raw = (item["NASDAQ100"] or "").strip()
        if raw in ("", "."):
            continue
        day = item[date_column].strip()
        date.fromisoformat(day)
        close = float(raw)
        if not math.isfinite(close) or close <= 0:
            raise ValueError("FRED_INVALID_INDEX_CLOSE")
        rows.append((day, close))
    if not rows or rows != sorted(rows) or len(set(d for d, _ in rows)) != len(rows):
        raise ValueError("FRED_DATES_NOT_UNIQUE_SORTED")
    return rows


def build(rows: list[tuple[str, float]], *, source_sha256: str, source_meta: dict | None = None) -> dict:
    if len(rows) < 254:
        raise ValueError("INDEX_NEEDS_253_SESSION_WARMUP")
    if rows != sorted(rows) or len({r[0] for r in rows}) != len(rows):
        raise ValueError("INDEX_DATES_NOT_SORTED")
    closes = [float(r[1]) for r in rows]
    if any(not math.isfinite(x) or x <= 0 for x in closes):
        raise ValueError("INVALID_INDEX_PRICE")
    level = None
    result = []
    first_investable = None
    for i, (day, close) in enumerate(rows):
        # A decision at prior close may only affect the NEXT session.
        # 253 completed closes are needed; index data begins in 1986.
        if i < 253:
            leverage = None
            signal = None
        else:
            features = compute_features(closes[i - 253:i])
            level = next_level(features, level)
            leverage = 0.0 if defense_active(features) else float(LEVEL_LEVERAGE[level])
            signal = rows[i - 1][0]
            if first_investable is None:
                first_investable = day
        result.append({"date": day, "close": round(close, 5), "l": leverage, "signal": signal})
    return {
        "schema_version": 1,
        "kind": KIND,
        "status": "RESEARCH_ONLY",
        "evidence": "OBSERVED_NDX_PRICE_INDEX_CLOSE_RETROACTIVE_SIGNAL_PROXY",
        "source": {"publisher": "FRED / Nasdaq, Inc.", "series": "NASDAQ100",
                   "url": SOURCE_URL, "download_sha256": source_sha256},
        "period": {"source_start": rows[0][0], "first_investable": first_investable,
                   "source_end": rows[-1][0], "source_rows": len(rows)},
        "strategy_semantics": "RETROACTIVE_RULE_APPLICATION_NOT_FROZEN_2009_REPLAY",
        "execution_semantics": "DAILY_CLOSE_TO_CLOSE_SYNTHETIC_EXPOSURE_NO_ETF_OHLC",
        "limitations": [
            "1986–2010 has NO observed TQQQ and 1986–1999 has NO QQQ.",
            "Nasdaq-100 price index excludes dividends; not a total-return benchmark.",
            "3x sleeve is a daily-reset synthetic 3x return, NOT historical TQQQ.",
            "Annual 3x drag is user-assumed; no observed historical financing or tracking.",
            "Index close-to-close prices cannot reconstruct next-open broker fills.",
            "Retroactive state initialized after 253 sessions, not original frozen 2009 start.",
            "No tax or Israeli after-tax performance calculated in this research panel.",
            "No broker trading, no performance prediction or live authorization."
        ],
        "rows": result,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", help="Optional FRED CSV input for offline audit")
    parser.add_argument("--out", default="docs/ndx1986-research.json")
    args = parser.parse_args()
    source_meta = None
    if args.csv:
        payload = Path(args.csv).read_bytes()
        rows = parse_fred_csv(payload)
    else:
        try:
            request = Request(SOURCE_URL, headers={"User-Agent": "StockLens research-only source-audit/1.0"})
            with urlopen(request, timeout=8) as response:
                payload = response.read(2_000_000)
            rows = parse_fred_csv(payload)
        except (TimeoutError, OSError) as exc:
            # FRED CSV occasionally stalls on GitHub runners. A separate
            # observed ^NDX Yahoo source is acceptable, but MUST be labeled.
            print("FRED_UNAVAILABLE_USING_SEPARATELY_LABELED_YAHOO_NDX_SOURCE:", type(exc).__name__)
            import yfinance as yf
            frame = yf.download("^NDX", start="1986-01-01", interval="1d",
                                auto_adjust=False, progress=False, actions=False, threads=False)
            if frame is None or frame.empty:
                raise RuntimeError("YAHOO_NDX_SOURCE_UNAVAILABLE") from exc
            close = frame["Close"]["^NDX"] if hasattr(frame.columns, "nlevels") and frame.columns.nlevels>1 else frame["Close"]
            rows = [(day.date().isoformat(), float(value))
                    for day, value in close.items()
                    if day.date().isoformat() >= "1986-01-02" and math.isfinite(float(value)) and float(value)>0]
            payload = ("DATE,NASDAQ100"+chr(10)+"".join(f"{day},{value:.12g}"+chr(10) for day,value in rows)).encode("utf-8")
            source_meta = {"publisher": "Yahoo Finance / Nasdaq, Inc.", "series": "^NDX",
                           "url": "https://finance.yahoo.com/quote/%5ENDX/history/",
                           "download_sha256": hashlib.sha256(payload).hexdigest(),
                           "method": "YFINANCE_NDX_CANONICAL_CLOSE_CSV_SHA256"}
    if rows[0][0] != "1986-01-02" or len(rows) < 9000:
        raise ValueError("NDX_1986_SOURCE_COVERAGE_INCOMPLETE")
    report = build(rows, source_sha256=hashlib.sha256(payload).hexdigest(), source_meta=source_meta)
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "period": report["period"],
                      "sha256": report["source"]["download_sha256"], "out": str(target)}))


if __name__ == "__main__":
    main()

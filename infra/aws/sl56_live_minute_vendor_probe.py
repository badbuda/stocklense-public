#!/usr/bin/env python3
"""Independent live Yahoo minute coverage probe; absolutely no AWS side effects.

This probe does NOT create historical Paper, override missing bars or certify
execution. It tests whether the existing frozen StockLens paper engine can
obtain the exact 09:31/09:32 and near-close bars for recent completed NYSE
sessions *right now* instead of waiting for nightly Lambda.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import sys

from stocklens import paper

SYMBOLS = ("QQQ", "TQQQ")


def verify_session(session: str, fetch=None) -> dict:
    date.fromisoformat(session)
    fetch = fetch or paper._fetch_intraday
    end = date.fromisoformat(session) + timedelta(days=1)
    result = {}
    for symbol in SYMBOLS:
        try:
            bars = fetch(symbol, date.fromisoformat(session), end,
                         expected_session=session)
            p31 = paper._bar_open(bars, session, 9, 31, symbol)
            p32 = paper._bar_open(bars, session, 9, 32, symbol)
            close = paper._eod_close(bars, session, symbol)
            day = bars[bars.index.date == date.fromisoformat(session)]
            digest = hashlib.sha256(day[["Open", "Close"]].to_csv().encode()).hexdigest()
            result[symbol] = {"status": "REAL_MINUTE_COVERAGE_PASS",
                              "unique_regular_minutes": len(day),
                              "has_0931_and_0932": p31 > 0 and p32 > 0,
                              "near_close_verified": close > 0,
                              "observed_bars_sha256": digest}
        except Exception as exc:
            result[symbol] = {"status": "INCOMPLETE_NO_PAPER",
                              "exception_class": type(exc).__name__,
                              "reason": str(exc)[:180]}
    return {
        "session": session,
        "qualified": all(x["status"] == "REAL_MINUTE_COVERAGE_PASS"
                         for x in result.values()),
        "symbols": result, "aws_mutations": False,
        "paper_receipts_created": False, "broker_orders": False,
    }


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", action="append", required=True)
    args = parser.parse_args(argv)
    out = {"kind": "STOCKLENS_EXECUTION_MINUTE_VENDOR_LIVE_FALSIFICATION",
           "checked_utc": datetime.now(timezone.utc).isoformat(),
           "observations": [verify_session(s) for s in args.session],
           "no_paper_backfill": True, "aws_mutations": False,
           "broker_orders": False}
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if all(x["qualified"] for x in out["observations"]) else 2


if __name__ == "__main__":
    sys.exit(main())

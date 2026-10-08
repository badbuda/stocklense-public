"""Observed ETF daily price integrity and exchange-calendar coverage.

This is a data QUALITY gate, not independent price-vendor verification, a
proof of historical no-lookahead selection, or an executable broker fill.
"""
from __future__ import annotations
import csv
import hashlib
import json
import math
from datetime import date
from pathlib import Path

SOURCE = Path("research/data/observed_etf_qqq_tqqq_adjusted.csv")
REPORT = Path("research/tradable_tqqq_execution_comparison.json")
PUBLIC = Path("docs/observed_etf_calendar_integrity.json")
RESEARCH = Path("research/observed_etf_calendar_integrity.json")
COLUMNS = ["date", "qqq_adjusted_open", "qqq_adjusted_close",
           "tqqq_adjusted_open", "tqqq_adjusted_close"]


def audit(rows: list[dict], expected_dates: list[str]) -> dict:
    seen = []
    bad_rows = []
    suspicious_moves = []
    previous = None
    for number, row in enumerate(rows, 2):
        try:
            d = str(row["date"])
            if date.fromisoformat(d).isoformat() != d:
                raise ValueError("BAD_DATE")
            values = [float(row[k]) for k in COLUMNS[1:]]
            if not all(math.isfinite(x) and x > 0 for x in values):
                raise ValueError("INVALID_PRICE")
            if seen and d <= seen[-1]:
                raise ValueError("NONMONOTONIC_OR_DUPLICATE_DATE")
            if previous:
                for symbol, i in (("QQQ", 2), ("TQQQ", 4)):
                    daily = values[i - 1] / previous[i - 1] - 1.0
                    # A >60% ETF day is an audit warning, never silently clipped.
                    if abs(daily) > 0.60:
                        suspicious_moves.append({
                            "date": d, "symbol": symbol,
                            "adjusted_close_return": daily
                        })
            seen.append(d)
            previous = values
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            bad_rows.append({"line": number, "reason": str(exc)[:90]})
    observed = set(seen)
    exchange = set(expected_dates)
    missing = sorted(exchange - observed)
    unexpected = sorted(observed - exchange)
    failures = []
    if not rows or bad_rows:
        failures.append("SCHEMA_PRICE_OR_DATE_INVALID")
    if missing:
        failures.append("MISSING_COMPLETED_EXCHANGE_SESSIONS")
    if unexpected:
        failures.append("UNEXPECTED_NONEXCHANGE_DATES")
    if len(seen) != len(rows):
        failures.append("UNREADABLE_SESSIONS")
    return {
        "status": "PASS" if not failures else "FAIL",
        "observed_sessions": len(rows),
        "expected_exchange_sessions": len(expected_dates),
        "first_date": seen[0] if seen else None,
        "last_date": seen[-1] if seen else None,
        "missing_sessions": missing,
        "unexpected_sessions": unexpected,
        "bad_rows": bad_rows,
        "large_daily_move_review_flags": suspicious_moves,
        "failures": failures,
        "synthetic_price_substitution": False,
        "independent_vendor_price_validation": False,
        "corporate_action_live_parity": False,
        "broker_fills_verified": False,
    }


def build(source=SOURCE, report=REPORT, research=RESEARCH, public=PUBLIC):
    import exchange_calendars as xcals

    raw = Path(source).read_bytes()
    evidence = json.loads(Path(report).read_text(encoding="utf-8"))
    provenance = evidence.get("observed_price_snapshot") or {}
    if provenance.get("sha256") != hashlib.sha256(raw).hexdigest():
        raise RuntimeError("DAILY_ETF_SOURCE_FINGERPRINT_MISMATCH")
    if provenance.get("independent_vendor_verified") is not False:
        raise RuntimeError("FALSE_INDEPENDENT_VENDOR_CLAIM")
    content = raw.decode("utf-8")
    with Path(source).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames != COLUMNS:
            raise RuntimeError("DAILY_ETF_PRICE_COLUMNS_INVALID")
        rows = list(reader)
    if not rows:
        raise RuntimeError("DAILY_ETF_EMPTY")
    start, end = rows[0]["date"], rows[-1]["date"]
    if start != evidence.get("period", {}).get("start") or end != evidence.get("period", {}).get("end"):
        raise RuntimeError("DAILY_ETF_WINDOW_MISMATCH")
    cal = xcals.get_calendar("XNYS")
    expected = [str(x.date()) for x in cal.sessions_in_range(start, end)]
    result = audit(rows, expected)
    result.update({
        "schema_version": 1,
        "kind": "OBSERVED_ETF_XNYS_CALENDAR_AND_PRICE_COHORT",
        "source_sha256": provenance["sha256"],
        "period": evidence.get("period"),
        "source": "DERIVED_YAHOO_ADJUSTED_DAILY_ETF_PRICE_SNAPSHOT",
        "audited_at_utc": __import__("datetime").datetime.now(
            __import__("datetime").timezone.utc).isoformat(),
        "warning": "Cohort completeness and format only. Independent provider, true point-in-time availability, corporate actions, 09:31/09:32 fills and broker order reconciliation remain unverified.",
    })
    if result["observed_sessions"] != provenance.get("rows"):
        result["failures"].append("SNAPSHOT_ROW_COUNT_MISMATCH")
        result["status"] = "FAIL"
    for out in (research, public):
        p = Path(out)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "missing": len(result["missing_sessions"]),
                      "unexpected": len(result["unexpected_sessions"]), "review_moves": len(result["large_daily_move_review_flags"])}))
    if result["status"] != "PASS":
        raise RuntimeError("OBSERVED_ETF_CALENDAR_INTEGRITY_FAILED:" + ",".join(result["failures"]))
    return result


if __name__ == "__main__":
    build()

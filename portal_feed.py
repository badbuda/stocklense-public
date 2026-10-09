"""Publish a compact, verified UI feed from the historical observed-ETF proxy.

No Yahoo or broker call here: the upstream Shadow run already downloaded observed
QQQ/TQQQ bars and computed the frozen strategy's historical execution proxy.
This step only projects existing audited source report; it never simulates TQQQ
by multiplying QQQ returns.
"""
from __future__ import annotations
import hashlib
import csv
import json
from pathlib import Path

SOURCE = Path("docs/tradable_tqqq_execution_comparison.json")
OUT = Path("docs/portal-history.json")


def build(report: dict) -> dict:
    if report.get("status") != "PASS" or report.get("kind") != "OBSERVED_QQQ_TQQQ_DAILY_OPEN_EXECUTION_PROXY":
        raise ValueError("HISTORICAL_SOURCE_NOT_PASS")
    if report.get("observed_instruments") != ["QQQ", "TQQQ"] or report.get("broker_fills_observed") is not False:
        raise ValueError("REAL_ETF_OR_BROKER_EVIDENCE_NOT_VERIFIED")
    cohort = report["no_contributions"]
    rows = cohort.get("daily_nav_rows", [])
    if len(rows) != cohort["sessions"] or len(rows) < 20:
        raise ValueError("NO_COMPLETE_REAL_ETF_NAV_ROWS")
    if rows[0]["date"] != cohort["start"] or rows[-1]["date"] != cohort["end"]:
        raise ValueError("REAL_ETF_DATE_RANGE_MISMATCH")
    if [r["date"] for r in rows] != sorted(set(r["date"] for r in rows)):
        raise ValueError("NONMONOTONIC_ETF_DATES")
    if abs(rows[-1]["stocklens_nav"] - cohort["stocklens"]["ending_equity"]) > 0.01:
        raise ValueError("ENDING_EQUITY_MISMATCH")
    if abs(rows[-1]["qqq_nav"] - cohort["qqq_buy_hold"]["ending_equity"]) > 0.01:
        raise ValueError("QQQ_EQUITY_MISMATCH")
    if any(x.get("stocklens_nav", 0) <= 0 or x.get("qqq_nav", 0) <= 0 for x in rows):
        raise ValueError("INVALID_NAV_DATA")
    # Only attach Yahoo OHLC when the exact price snapshot matches the audited
    # source report. Never construct fake 3x TQQQ price history from QQQ.
    price_file = Path("research/data/observed_etf_qqq_tqqq_adjusted.csv")
    matched_prices = {}
    if price_file.is_file():
        snapshot = price_file.read_bytes()
        if hashlib.sha256(snapshot).hexdigest() != report["observed_price_snapshot"]["sha256"]:
            raise ValueError("YAHOO_PRICE_SNAPSHOT_HASH_DRIFT")
        with price_file.open(newline="", encoding="utf-8") as fh:
            for entry in csv.DictReader(fh):
                matched_prices[entry["date"]] = {
                    "qo": float(entry["qqq_adjusted_open"]),
                    "qc": float(entry["qqq_adjusted_close"]),
                    "to": float(entry["tqqq_adjusted_open"]),
                    "tc": float(entry["tqqq_adjusted_close"]),
                }
        if len(matched_prices) != len(rows):
            raise ValueError("YAHOO_PRICE_SNAPSHOT_SESSION_MISMATCH")
    compact = [
        {"date": r["date"], "s": round(r["stocklens_nav"], 2),
         "q": round(r["qqq_nav"], 2), **matched_prices.get(r["date"], {}),
         "l": r["leverage"],
         "signal": r["effective_prior_signal_date"],
         "contribution": r["contribution"],
         "rebalance": r["rebalance"]}
        for r in rows
    ]
    result = {
        "schema_version": 1, "evidence": "REAL_QQQ_TQQQ_ADJUSTED_DAILY_OPEN_EXECUTION_PROXY",
        "instruments": ["QQQ", "TQQQ"],
        "observed_ohlc_available": len(matched_prices) == len(rows),
        "source": report["price_source"],
        "snapshot_sha256": report["price_fingerprint_sha256"],
        "period": report["period"],
        "updated_session": cohort["end"],
        "basis": "Historical stocklens8 fixed decisions; next-session daily OPEN modeled execution; no broker fills",
        "limitations": report["limitations"],
        "initial_capital": 100_000,
        "daily": compact,
        "events": cohort.get("events", []),
        "without_contributions": {
            "strategy": cohort["stocklens"], "qqq": cohort["qqq_buy_hold"],
        },
        "with_monthly_contributions": {
            "monthly_usd": report["initial_100k_monthly_3500"]["monthly_contribution"],
            "strategy": report["initial_100k_monthly_3500"]["stocklens"],
            "qqq": report["initial_100k_monthly_3500"]["qqq_buy_hold"],
        },
        "cost_sensitivity": report["slippage_stress_no_contributions"],
        "execution_lag_sensitivity": report["signal_lag_stress_no_contributions"],
        "full_lean_broker_parity": False,
        "live_trading_authorized": False,
    }
    return result


def main() -> None:
    raw = SOURCE.read_bytes()
    report = json.loads(raw)
    result = build(report)
    result["report_content_sha256"] = hashlib.sha256(raw).hexdigest()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n",
                   encoding="utf-8")
    print(json.dumps({"status": "PASS", "rows": len(result["daily"]),
                      "end": result["updated_session"], "bytes": OUT.stat().st_size,
                      "uses_observed_etf": True, "broker_fills": False}))


if __name__ == "__main__":
    main()

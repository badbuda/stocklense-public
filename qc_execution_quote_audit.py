"""Audit native QuantConnect SIMULATED fills vs same-order submission quotes.

Private LEAN JSON stays local. Neither chart prices nor LEAN fill prices prove
broker execution. Directional fill/lastPrice delta is NOT market slippage.
Usage: python qc_execution_quote_audit.py NEW.json --prior OLD.json --out REPORT.json
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import median


def number(value, field):
    try:
        n = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("INVALID_" + field) from exc
    if not math.isfinite(n) or n <= 0:
        raise ValueError("INVALID_" + field)
    return n


def stats(values):
    if not values:
        return {"count": 0, "median_bps": None, "p95_bps": None, "min_bps": None, "max_bps": None}
    v = sorted(values)
    i = (len(v) - 1) * .95
    lo = int(i)
    p95 = v[lo] if lo == len(v) - 1 else v[lo] + (i - lo) * (v[lo + 1] - v[lo])
    return {"count": len(v), "median_bps": median(v), "p95_bps": p95,
            "min_bps": v[0], "max_bps": v[-1]}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def chart_series(chart, name):
    raw = chart.get("series", {}).get(name)
    if not isinstance(raw, dict):
        return {}
    result = {}
    for point in raw.get("values", []):
        if not isinstance(point, list) or len(point) != 2:
            raise ValueError("INVALID_CHART_POINT:" + name)
        instant = int(point[0])
        price = number(point[1], "CHART_PRICE")
        if instant in result:
            raise ValueError("DUPLICATE_CHART_TIMESTAMP:" + name)
        result[instant] = price
    return result


def timestamp(value):
    if not isinstance(value, str):
        raise ValueError("INVALID_ORDER_TIMESTAMP")
    try:
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_ORDER_TIMESTAMP") from exc


def audit(new_path, prior_path=None):
    current = json.loads(Path(new_path).read_bytes())
    orders = current.get("orders")
    if not isinstance(orders, dict):
        raise ValueError("MISSING_QC_ORDERS")
    rawchart = current.get("charts", {}).get("SL724_QC_EXECUTION_PRICES", {})
    probes = {name: chart_series(rawchart, name) for name in
              ("QQQ_0931", "TQQQ_0931", "TQQQ_0932")}
    rows, missing, flagged = [], [], []
    for oid, order in orders.items():
        if int(order.get("status", -1)) != 3:
            missing.append({"id": str(oid), "reason": "NOT_FILLED"})
            continue
        symbol = order.get("symbol", {}).get("value")
        if symbol not in ("QQQ", "QLD", "TQQQ"):
            missing.append({"id": str(oid), "reason": "UNEXPECTED_SECURITY"})
            continue
        qty = float(order.get("quantity", 0))
        if not math.isfinite(qty) or qty == 0:
            raise ValueError("INVALID_FILLED_QUANTITY:" + str(oid))
        fill = number(order.get("price"), "FILL_PRICE")
        quote = order.get("orderSubmissionData")
        if not isinstance(quote, dict):
            missing.append({"id": str(oid), "reason": "SUBMISSION_QUOTE_MISSING"})
            continue
        bid = number(quote.get("bidPrice"), "SUBMISSION_BID")
        ask = number(quote.get("askPrice"), "SUBMISSION_ASK")
        last = number(quote.get("lastPrice"), "SUBMISSION_LAST")
        if ask < bid:
            raise ValueError("CROSSED_SUBMISSION_QUOTES:" + str(oid))
        direction = 1 if qty > 0 else -1
        side = "BUY" if direction == 1 else "SELL"
        ref = ask if direction == 1 else bid
        order_time = order.get("time")
        instant = timestamp(order_time)
        side_bps = (fill / ref - 1) * 10000 * direction
        last_bps = (fill / last - 1) * 10000 * direction
        spread_bps = (ask - bid) / ((ask + bid) / 2) * 10000
        chartname = symbol + ("_0931" if ":31:" in order_time else "_0932")
        exact_price = probes.get(chartname, {}).get(instant)
        row = {
            "id": str(oid), "date": order_time[:10], "timestamp": order_time,
            "symbol": symbol, "side": side, "quantity": int(qty), "fill": fill,
            "submission_bid": bid, "submission_ask": ask, "submission_last": last,
            "fill_vs_side_quote_directional_bps": side_bps,
            "fill_vs_last_directional_bps_NOT_SLIPPAGE": last_bps,
            "submission_spread_bps": spread_bps,
            "exact_timestamp_chart_price": exact_price,
            "chart_exact_timestamp_available": exact_price is not None,
            "exact_timestamp_chart_vs_last_bps":
                (exact_price / last - 1) * 10000 if exact_price is not None else None,
        }
        rows.append(row)
        if abs(last_bps) > 50 or abs(side_bps) > 50 or spread_bps > 50:
            flagged.append(row)
    if not rows:
        raise ValueError("NO_VALID_QC_FILLS")
    by_symbol = {}
    for symbol in ("QQQ", "QLD", "TQQQ"):
        subset = [r for r in rows if r["symbol"] == symbol]
        by_symbol[symbol] = {
            "orders": len(subset), "sides": dict(Counter(r["side"] for r in subset)),
            "fill_vs_side_quote_directional": stats(
                [r["fill_vs_side_quote_directional_bps"] for r in subset]),
            "fill_vs_last_directional_NOT_SLIPPAGE": stats(
                [r["fill_vs_last_directional_bps_NOT_SLIPPAGE"] for r in subset]),
            "spread": stats([r["submission_spread_bps"] for r in subset]),
            "exact_timestamp_chart_join_count":
                sum(r["chart_exact_timestamp_available"] for r in subset),
        }
    comparison = None
    if prior_path is not None:
        prior = json.loads(Path(prior_path).read_bytes())
        equal = {key: current.get(key) == prior.get(key)
                 for key in ("orders", "statistics", "runtimeStatistics")}
        equal["observer_seven_feature_chart"] = (
            current.get("charts", {}).get("SL724_P0_FEATURES") ==
            prior.get("charts", {}).get("SL724_P0_FEATURES"))
        comparison = {"prior_sha256": digest(prior_path),
                      "identical": equal, "all_checked_identical": all(equal.values())}
    return {
        "schema_version": 1, "kind": "NATIVE_LEAN_SIMULATED_ORDER_SUBMISSION_QUOTE_AUDIT",
        "source_json_sha256": digest(new_path),
        "status": "AUDITED_WITH_EXECUTION_REALISM_BLOCKERS" if flagged
                  else "AUDITED_QUOTES_NOT_BROKER_PROOF",
        "total_reported_orders": len(orders),
        "orders_with_usable_side_quotes": len(rows),
        "excluded_or_incomplete_orders": missing,
        "chart_points": {name: len(values) for name, values in probes.items()},
        "by_symbol": by_symbol,
        "outlier_orders_over_50bps": sorted(
            flagged, key=lambda r: abs(r["fill_vs_last_directional_bps_NOT_SLIPPAGE"]),
            reverse=True),
        "outlier_count": len(flagged),
        "rerun_comparison": comparison,
        "quality_gates": {
            "complete_filled_order_quote_coverage": not missing and len(rows) == len(orders),
            "no_spread_or_fill_quote_outliers_over_50bps": not flagged,
            "strategy_unchanged_vs_prior":
                comparison is not None and comparison["all_checked_identical"],
        },
        "claims": {
            "measured_broker_slippage": False, "trade_fills_executable": False,
            "side_quote_is_independent_of_simulated_fill": False,
            "daily_yahoo_open_equals_0931_qc_quote": False,
            "live_trading_authorized": False,
        },
        "limitations": [
            "Bid, ask, last and simulated fill all originate from LEAN, not real executions.",
            "Directional fill-vs-last is NOT market slippage.",
            "Directional fill-vs-side-quote is diagnostic, not independently validated.",
            "Chart joins require identical UTC seconds, never same-day approximation.",
            "Outlying spreads and prints are kept for investigation, never clipped.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("new_json")
    parser.add_argument("--prior")
    parser.add_argument("--out", default="research/local/qc_execution_quote_audit.json")
    args = parser.parse_args()
    report = audit(args.new_json, args.prior)
    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "status", "total_reported_orders", "orders_with_usable_side_quotes",
        "outlier_count", "quality_gates")}, indent=2))


if __name__ == "__main__":
    main()

"""Original frozen SL724 QuantConnect simulated fill vs submission quote forensic.

The owner's FULL original Download Results JSON is PRIVATE, NOT in this
repository. Run locally with --original PATH; do not commit private JSON/CSV.
Source identity is locked to SHA256 of the original 2009-2024 LEAN result.
This is NOT a broker execution audit: orderSubmissionData bid/ask are from
LEAN and cannot certify true NBBO, executable fills or StockLens 8.0 live use.

CI can run deterministic synthetic tests without access to private material.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from statistics import median

from json_artifacts import write_json_atomic

PINNED_SL724_SHA256 = "65cb291e6552dc0f86b32106bc3fe3f7a7ed8a127b3d0d6f84a60a8f5800b6f7"
ORIGINAL_EXPECTED_FILLED_ORDERS = 345
ORIGINAL_EXPECTED_CHART_SESSIONS = 3774
REQUIRED_CHART_SERIES = ("Leverage", "NAV", "Drawdown")
SYMBOLS = ("QQQ", "QLD", "TQQQ")
THRESHOLD_BPS = 50.0
DEFAULT_OUT = Path("research/local/native_sl724_order_quote_forensics.json")


def _positive(value, field):
    try:
        x = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("INVALID_" + field) from exc
    if not math.isfinite(x) or x <= 0:
        raise ValueError("INVALID_" + field)
    return x


def _signed_quantity(value):
    try:
        q = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError("INVALID_ORDER_QUANTITY") from exc
    if not math.isfinite(q) or q == 0 or not q.is_integer():
        raise ValueError("INVALID_ORDER_QUANTITY")
    return int(q)


def _quantile(rows, frac):
    if not rows:
        return None
    sorted_values = sorted(rows)
    k = frac * (len(sorted_values) - 1)
    i = int(k)
    return sorted_values[i] if i + 1 == len(rows) else (
        sorted_values[i] + (k - i) * (sorted_values[i+1] - sorted_values[i])
    )


def _summary(values):
    return {
        "count":len(values),
        "median_bps":median(values) if values else None,
        "p95_bps":_quantile(values,.95),
        "min_bps":min(values) if values else None,
        "max_bps":max(values) if values else None,
        "absolute_over_50bps_count":sum(abs(x)>THRESHOLD_BPS for x in values),
    }


def _timestamp_utc(value):
    if not isinstance(value, str) or not value:
        raise ValueError("INVALID_ORDER_UTC_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value.replace("Z","+00:00"))
        if parsed.tzinfo is None or parsed.utcoffset() is None:
            raise ValueError("naive")
        return parsed.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise ValueError("INVALID_ORDER_UTC_TIMESTAMP") from exc


def extract_native_orders(raw, *, lock_original=True):
    """Validate native order data, not an independent external order source."""
    charts = raw.get("charts")
    if not isinstance(charts, dict):
        raise ValueError("MISSING_NATIVE_LEAN_CHARTS")
    series = charts.get("SL724",{}).get("series",{})
    if not isinstance(series,dict):
        raise ValueError("MISSING_NATIVE_LEAN_SL724_CHART")
    points = {}
    for name in REQUIRED_CHART_SERIES:
        vals = series.get(name,{}).get("values")
        if not isinstance(vals,list):
            raise ValueError("MISSING_NATIVE_CHART_SERIES:"+name)
        points[name]=len(vals)
    if len(set(points.values()))!=1:
        raise ValueError("SL724_CHART_LENGTH_DRIFT")
    if lock_original and points["Leverage"] != ORIGINAL_EXPECTED_CHART_SESSIONS:
        raise ValueError("ORIGINAL_SL724_DAILY_SESSION_COUNT_DRIFT")
    orders = raw.get("orders")
    if not isinstance(orders,dict) or not orders:
        raise ValueError("MISSING_NATIVE_LEAN_ORDERS")
    if lock_original and len(orders)!=ORIGINAL_EXPECTED_FILLED_ORDERS:
        raise ValueError("ORIGINAL_SL724_ORDER_COUNT_DRIFT")
    records=[]
    for key,order in orders.items():
        if not isinstance(order,dict):
            raise ValueError("BAD_NATIVE_ORDER:"+str(key))
        if str(order.get("id"))!=str(key):
            raise ValueError("NATIVE_ORDER_ID_MISMATCH:"+str(key))
        if order.get("status")!=3:
            raise ValueError("NOT_FILLED_ORIGINAL_ORDER:"+str(key))
        symbol=order.get("symbol",{}).get("value")
        if symbol not in SYMBOLS:
            raise ValueError("UNEXPECTED_NATIVE_SECURITY:"+str(key))
        quantity=_signed_quantity(order.get("quantity"))
        side="BUY" if quantity>0 else "SELL"
        fill=_positive(order.get("price"),"SIMULATED_FILL_PRICE")
        quote=order.get("orderSubmissionData")
        if not isinstance(quote,dict):
            raise ValueError("NATIVE_SUBMISSION_QUOTE_MISSING")
        bid=_positive(quote.get("bidPrice"),"SIMULATED_BID")
        ask=_positive(quote.get("askPrice"),"SIMULATED_ASK")
        last=_positive(quote.get("lastPrice"),"SIMULATED_LAST")
        if ask<bid:
            raise ValueError("SIMULATED_CROSSED_BID_ASK")
        instant=_timestamp_utc(order.get("time"))
        direction=1 if quantity>0 else -1
        quote_ref=ask if quantity>0 else bid
        side_bps=(fill/quote_ref-1)*10000*direction
        last_bps=(fill/last-1)*10000*direction
        spread_bps=(ask-bid)/((bid+ask)/2)*10000
        if not all(math.isfinite(x) for x in (side_bps,last_bps,spread_bps)):
            raise ValueError("NONFINITE_EXECUTION_DIAGNOSTIC")
        records.append({
            "order_id":str(key),
            "year":instant.year,
            "symbol":symbol,
            "side":side,
            "quantity":quantity,
            "simulated_fill_vs_submission_side_quote_bps":side_bps,
            "simulated_fill_vs_submission_last_bps_NOT_SLIPPAGE":last_bps,
            "simulated_submission_spread_bps":spread_bps,
            "quote_reference_notional":abs(quantity)*quote_ref,
            "order_utc":instant.isoformat(),
            "is_LEAN_internal_quote_not_NBBO":True,
        })
    return points,records


def evaluate(raw, raw_bytes, *, expected_sha=None):
    digest=hashlib.sha256(raw_bytes).hexdigest()
    if expected_sha and digest!=expected_sha:
        raise ValueError("LOCKED_ORIGINAL_SOURCE_SHA256_MISMATCH")
    is_locked=digest==PINNED_SL724_SHA256
    if expected_sha is None and not is_locked:
        raise ValueError("ORIGINAL_SOURCE_NOT_LOCKED")
    points,records=extract_native_orders(raw,lock_original=is_locked)
    if is_locked and len(records)!=ORIGINAL_EXPECTED_FILLED_ORDERS:
        raise ValueError("LOCKED_ORIGINAL_ORDER_COUNT_DRIFT")
    result={}
    flagged=[]
    for name in (*SYMBOLS,"ALL"):
        group=[r for r in records if name=="ALL" or r["symbol"]==name]
        if not group and is_locked:
            raise ValueError("MISSING_ORIGINAL_SECURITY:"+name)
        values=[r["simulated_fill_vs_submission_side_quote_bps"] for r in group]
        lastvals=[r["simulated_fill_vs_submission_last_bps_NOT_SLIPPAGE"] for r in group]
        spreads=[r["simulated_submission_spread_bps"] for r in group]
        result[name]={
            "simulated_orders":len(group),
            "buy_orders":sum(r["side"]=="BUY" for r in group),
            "sell_orders":sum(r["side"]=="SELL" for r in group),
            "fill_vs_submission_side_quote":_summary(values),
            "fill_vs_last_NOT_SLIPPAGE":_summary(lastvals),
            "submission_spread":_summary(spreads),
            "quoted_side_notional_weighted_bps":(
                sum(r["simulated_fill_vs_submission_side_quote_bps"]*r["quote_reference_notional"]
                    for r in group)/sum(r["quote_reference_notional"] for r in group)
                if group else None),
        }
    for r in records:
        if (abs(r["simulated_fill_vs_submission_side_quote_bps"])>THRESHOLD_BPS
            or abs(r["simulated_fill_vs_submission_last_bps_NOT_SLIPPAGE"])>THRESHOLD_BPS
            or r["simulated_submission_spread_bps"]>THRESHOLD_BPS):
            flagged.append({
                "year":r["year"],"symbol":r["symbol"],"side":r["side"],
                "fill_side_quote_bps":r["simulated_fill_vs_submission_side_quote_bps"],
                "fill_last_bps_NOT_SLIPPAGE":r["simulated_fill_vs_submission_last_bps_NOT_SLIPPAGE"],
                "internal_submission_spread_bps":r["simulated_submission_spread_bps"],
                # Do not write raw order ids, native timestamps, individual quotes,
                # account identifiers or holdings to report.
            })
    return {
        "schema_version":1,
        "kind":"LOCKED_NATIVE_LEAN_SIMULATED_FILL_VS_INTERNAL_QUOTE_FORENSICS",
        "status":"LOCKED_ORIGINAL_LEAN_ORDER_QUOTE_REVIEW" if is_locked
                 else "SYNTHETIC_TEST_FIXTURE_NOT_ORIGINAL",
        "source_original_sha256_matched":is_locked,
        "source_sha256":digest,
        "native_order_count":len(records),
        "original_LEAN_chart_series_points":points,
        "statistics_by_security":result,
        "outlier_50bps_any_diagnostic_count":len(flagged),
        "outlier_records_aggregated_no_private_order_identity":flagged[:20],
        "original_native_daily_features_present":False,
        "native_source_code_identity_proven":False,
        "independent_executable_NBBO_verified":False,
        "actual_broker_fills_observed":False,
        "same_input_state_and_CAGR_parity_proven":False,
        "automatic_live_trading_authorized":False,
        "risk_note":"LEAN orderSubmissionData bid/ask/last and fill prices share the same QC simulation source; none are an independent venue quote or actual broker execution. Directional fill vs last MUST NOT be called realized slippage.",
    }


def audit_file(path, *, expected_sha=None, out=DEFAULT_OUT):
    blob=Path(path).read_bytes()
    original=json.loads(blob)
    report=evaluate(original,blob,expected_sha=expected_sha)
    out=Path(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    write_json_atomic(out,report)
    return report


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original",required=True,
                   help="PRIVATE original frozen QC Download Results JSON path; never upload to GitHub")
    p.add_argument("--out",default=str(DEFAULT_OUT),
                   help="Local private aggregate report (defaults to ignored research/local)")
    a=p.parse_args()
    report=audit_file(a.original,out=a.out)
    print(json.dumps({
        "status":report["status"],"source_hash_locked":report["source_original_sha256_matched"],
        "orders":report["native_order_count"],
        "outliers":report["outlier_50bps_any_diagnostic_count"],
        "by_symbol":report["statistics_by_security"],
        "broker_quotes_verified":False,"live_trading_authorized":False,
    },indent=2))


if __name__=="__main__":
    main()

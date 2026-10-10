"""Private original LEAN P1 order/position/cash ledger reconciliation.

Uses ONLY the owner's original SHA-pinned 7.24 run and observer P1 native QC
plot. No QQQ/QLD/TQQQ synthetic prices, fabricated broker fills, or claims
of independent venue execution. Output is aggregate evidence only; do NOT
check private 3774-day rows or full order JSON into the public repository.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path

from qc_private_lean_portfolio_acquisition import project
from json_artifacts import write_json_atomic

TICKERS={"QQQ":"qqq_quantity","QLD":"qld_quantity","TQQQ":"tqqq_quantity"}
START_CASH=100000.
EXPECTED_ORDERS=345
FEE_RECONCILIATION_ABS_TOL_USD=.02
NONTRADE_FEE_ABS_TOL_USD=.001


def _safe_float(value,kind):
    try:
        v=float(value)
    except (ValueError,TypeError,OverflowError) as exc:
        raise ValueError("P1_NATIVE_INVALID_NUMBER:"+kind) from exc
    if not math.isfinite(v):
        raise ValueError("P1_NATIVE_NONFINITE_NUMBER:"+kind)
    return v


def _reported_fee(stats):
    source=stats.get("Total Fees")
    if not isinstance(source,str):
        raise ValueError("P1_MISSING_NATIVE_TOTAL_FEES")
    return _safe_float(source.replace("$","").replace(",",""),"reported_total_fees")


def reconcile(rows, native_orders, original_statistics,*,lock_original_counts=True):
    if not isinstance(rows,list) or len(rows)<2:
        raise ValueError("P1_MISSING_NATIVE_ACCOUNT_ROWS")
    if not isinstance(native_orders,dict):
        raise ValueError("P1_MISSING_NATIVE_FILLED_ORDERS")
    if lock_original_counts and (len(rows)!=3774 or len(native_orders)!=EXPECTED_ORDERS):
        raise ValueError("P1_ORIGINAL_SESSION_OR_ORDER_COUNT_DRIFT")
    by_date=defaultdict(list)
    allowed_dates={r["date"] for r in rows}
    if len(allowed_dates)!=len(rows):
        raise ValueError("P1_DUPLICATE_ACCOUNT_SESSION")
    if [r["date"] for r in rows]!=sorted(allowed_dates):
        raise ValueError("P1_UNSORTED_ACCOUNT_SESSION")
    for oid,order in native_orders.items():
        if not isinstance(order,dict) or str(order.get("id"))!=str(oid):
            raise ValueError("P1_NATIVE_ORDER_ID_INVALID")
        if order.get("status")!=3:
            raise ValueError("P1_NATIVE_ORDER_NOT_FILLED")
        symbol=order.get("symbol",{}).get("value")
        if symbol not in TICKERS:
            raise ValueError("P1_UNEXPECTED_NATIVE_ORDER_SYMBOL")
        time=order.get("time")
        if not isinstance(time,str) or len(time)<10:
            raise ValueError("P1_NATIVE_ORDER_TIME_MISSING")
        when=time[:10]
        try:
            date.fromisoformat(when)
        except ValueError as exc:
            raise ValueError("P1_INVALID_ORDER_UTC_DAY") from exc
        if when not in allowed_dates:
            raise ValueError("P1_ORDER_OUTSIDE_ORIGINAL_CHART_RANGE:"+when)
        shares=_safe_float(order.get("quantity"),"quantity")
        value=_safe_float(order.get("value"),"value")
        price=_safe_float(order.get("price"),"price")
        if not shares or not shares.is_integer() or price<=0:
            raise ValueError("P1_UNEXECUTABLE_ORDER_QUANTITY_OR_PRICE")
        if value*shares<=0:
            raise ValueError("P1_ORDER_NOTIONAL_SIGN_OR_ZERO")
        if not math.isclose(value,shares*price,rel_tol=1e-12,abs_tol=1e-8):
            raise ValueError("P1_NATIVE_ORDER_NOTIONAL_NOT_QUANTITY_TIMES_FILL")
        by_date[when].append((symbol,shares,value))
    positions={s:0. for s in TICKERS}
    previous_cash=START_CASH
    previous_contrib=START_CASH
    share_checks=0
    trade_day_count=0
    no_order_days=0
    deposit_count=0
    fees_implied=0.
    worst_fee_vs_fill=[]
    for r in rows:
        when=r["date"]
        activity=by_date[when]
        for sym,key in TICKERS.items():
            positions[sym]+=sum(qty for ticker,qty,_ in activity if ticker==sym)
            actual=_safe_float(r.get(key),key)
            share_checks+=1
            if not math.isclose(positions[sym],actual,rel_tol=0,abs_tol=1e-6):
                raise ValueError("P1_NATIVE_SHARE_LEDGER_MISMATCH:"+when+":"+sym)
        cash=_safe_float(r.get("cash"),"cash")
        contributed=_safe_float(r.get("contributed"),"contributed")
        if contributed<previous_contrib-.001:
            raise ValueError("P1_EXTERNAL_CONTRIBUTED_CAPITAL_DECREASED")
        inflow=contributed-previous_contrib
        if inflow>.5:
            if not math.isclose(inflow,3500.,abs_tol=.5):
                raise ValueError("P1_BAD_MONTHLY_CONTRIBUTION")
            deposit_count+=1
        elif abs(inflow)>.5:
            raise ValueError("P1_BAD_NONMONTHLY_CONTRIBUTION")
        net_value=sum(notional for _,_,notional in activity)
        native_implied_day_fee=previous_cash+inflow-net_value-cash
        if activity:
            trade_day_count+=1
            if native_implied_day_fee < -NONTRADE_FEE_ABS_TOL_USD:
                raise ValueError("P1_NEGATIVE_FEE_DURING_ORDER_SESSION:"+when)
            naive_fee=.0002*sum(abs(v) for _,_,v in activity)
            worst_fee_vs_fill.append((abs(naive_fee-native_implied_day_fee),
                                      when,round(native_implied_day_fee,6),
                                      round(naive_fee,6)))
        else:
            no_order_days+=1
            if abs(native_implied_day_fee)>NONTRADE_FEE_ABS_TOL_USD:
                raise ValueError("P1_UNEXPLAINED_NONTRADE_CASH_MOVEMENT:"+when)
        fees_implied+=native_implied_day_fee
        previous_cash=cash
        previous_contrib=contributed
    native_fees=_reported_fee(original_statistics)
    if abs(fees_implied-native_fees)>FEE_RECONCILIATION_ABS_TOL_USD:
        raise ValueError("P1_NATIVE_TOTAL_FEE_CASH_RECONCILIATION_FAILED")
    if lock_original_counts:
        if deposit_count!=179 or abs(previous_contrib-726500.)>.5:
            raise ValueError("P1_CONTRIBUTION_COUNT_OR_TOTAL_MISMATCH")
    return {
        "status":"ORIGINAL_LEAN_P1_NATIVE_ORDER_AND_CHART_LEDGER_RECONCILED",
        "verified_native_plot_sessions":len(rows),
        "native_filled_orders":len(native_orders),
        "checked_daily_etf_share_states":share_checks,
        "all_share_quantities_match_original_filled_order_cumulative_ledger":True,
        "maximum_share_difference":0.,
        "days_with_native_fills":trade_day_count,
        "days_without_fills":no_order_days,
        "deposits":deposit_count,
        "cumulative_external_capital":previous_contrib,
        "native_fees_inferred_from_plot_cash_orders_and_contributions":fees_implied,
        "original_lean_reported_total_fees":native_fees,
        "fee_total_reconciliation_absolute_USD":abs(fees_implied-native_fees),
        "all_days_without_orders_have_no_unexplained_cash_delta":True,
        "worst_five_fee_deviations_from_naive_fill_notional": [
            {"day":d,"abs_difference_USD":e,
             "implied_native_day_fee_USD":f,"2bps_executed_notional_USD":naive}
            for e,d,f,naive in sorted(worst_fee_vs_fill,reverse=True)[:5]],
        "fee_attribution_qualification":
          "LEAN original BpsFeeModel charges abs(order.quantity) * SECURITY.PRICE * 2bps, which can differ from filled order notional. Daily fees here are inferred from native plotted cash and signed native fills; individual original fee records not proven.",
        "no_independent_raw_venue_prices":True,
        "actual_broker_fills_observed":False,
        "original_2024_08_30_end_account_chart_confirmed":False,
        "independent_same_start_python_portfolio_parity_proven":False,
        "capital_deployment_authorized":False,
    }


def audit(original_json,observer_json,*,out="research/local/p1_native_ledger_evidence_PRIVATE.json"):
    rows,chart=project(original_json,observer_json)
    original=json.loads(Path(original_json).read_bytes())
    rerun=json.loads(Path(observer_json).read_bytes())
    ledger=reconcile(rows,rerun["orders"],original["statistics"])
    ledger["source_original_sha256"]=hashlib.sha256(Path(original_json).read_bytes()).hexdigest()
    ledger["source_observer_sha256"]=hashlib.sha256(Path(observer_json).read_bytes()).hexdigest()
    ledger["native_plot_original_SL724_PARITY"]=chart["all_original_chart_timestamps_reconciled"]
    ledger["native_legend_and_cashflow_parity"]=chart["status"]
    ledger["P1_run_end_status"]=chart["endpoint_reconciliation"]["status"]
    ledger["source_compiled_build_attestation_proven"]=False
    ledger["original_2024_08_30_end_account_chart_confirmed"]=chart["endpoint_reconciliation"]["end_of_run_equity_match_proven"]
    write_json_atomic(out,ledger)
    return ledger


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original",required=True)
    p.add_argument("--observer",required=True)
    p.add_argument("--out",default="research/local/p1_native_ledger_evidence_PRIVATE.json")
    a=p.parse_args()
    report=audit(a.original,a.observer,out=a.out)
    print(json.dumps({"status":report["status"],
        "etf_quantity_checks":report["checked_daily_etf_share_states"],
        "native_fees_match_total":report["fee_total_reconciliation_absolute_USD"]<.02,
        "full_end_of_run_broker_PARITY_proven":False,
        "capital_deployment_authorized":False},indent=2))

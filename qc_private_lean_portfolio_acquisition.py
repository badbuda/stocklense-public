"""Strict PRIVATE P1 native QuantConnect 7.24 daily portfolio-chart importer.

P1 is a separate observer-only rerun of frozen 7.24. It does NOT reconstruct
broker fills, reverse engineer QLD/TQQQ positions from Yahoo, or certify a
same-start independent Python portfolio path. Original P0/P1 native plot data
must remain private, not public repository artifacts.

Provenance:
  - original SL724 result SHA-256 is pinned in qc_original_lean_chart_audit
  - 345 order objects, SL724 original charts, stats, daily rolling windows,
    and 301 closed trade economics must be unchanged versus original
  - native portfolio chart must be complete and time-aligned with every one
    of the 3,774 original SL724 CLOSE observations.
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

from qc_original_lean_chart_audit import extract
from qc_chart_feature_acquisition import compare_original_rerun_invariants
from json_artifacts import write_json_atomic

CHART = "SL724_P1_PORTFOLIO"
COLUMNS = ("date", "equity", "cash", "qqq_quantity", "qld_quantity",
           "tqqq_quantity", "units", "contributed", "holdings_value")
RAW_PLOTS = COLUMNS[1:-1]
DEFAULT_CSV = Path("research/local/qc_lean_p1_daily_portfolio_PRIVATE.csv")
DEFAULT_AUDIT = Path("research/local/qc_lean_p1_daily_portfolio_audit_PRIVATE.json")
INITIAL_CAPITAL = 100000.
MONTHLY_DEPOSIT = 3500.
EXPECTED_DEPOSITS = 179
EXPECTED_CONTRIBUTED = INITIAL_CAPITAL + MONTHLY_DEPOSIT*EXPECTED_DEPOSITS
NAV_ABS_TOL = .02   # chart precision unknown; NOT equality of unrounded NAV
NAV_REL_TOL = 2e-4  # conservative bound for LEAN custom chart quantization
EQUITY_END_REL_TOL = 1e-6
CASH_END_REL_TOL = 1e-6


def _num(value, name):
    try:
        v = float(value)
    except (ValueError, TypeError, OverflowError) as exc:
        raise ValueError("LEAN_P1_INVALID_CHART_NUMBER:"+name) from exc
    if not math.isfinite(v):
        raise ValueError("LEAN_P1_NONFINITE_CHART_NUMBER:"+name)
    return v


def _pct_stats(rows, original):
    out = {"observations": len(rows),
           "first_session": rows[0]["date"],
           "last_session": rows[-1]["date"],
           "unrounded_native_feature_precision_proven":False,
           "real_broker_execution_proven":False}
    parsed = json.loads(Path(original).read_bytes())
    end_equity = _num(str(parsed["statistics"]["End Equity"]).replace(",",""), "NATIVE_END_EQUITY")
    ending = rows[-1]["equity"]
    difference = abs(end_equity-ending)
    if difference > max(1., abs(end_equity)*EQUITY_END_REL_TOL):
        raise ValueError("LEAN_P1_END_EQUITY_NOT_ORIGINAL")
    runtime=parsed.get("runtimeStatistics",{})
    holdings_raw=runtime.get("Holdings")
    if isinstance(holdings_raw,str) and holdings_raw:
        holdings = _num(holdings_raw.replace("$","").replace(",",""),"ORIGINAL_END_HOLDINGS")
        inferred=rows[-1]["holdings_value"]
        if abs(holdings-inferred)>max(1.,abs(holdings)*CASH_END_REL_TOL):
            raise ValueError("LEAN_P1_END_HOLDINGS_NOT_ORIGINAL")
        out["ending_original_runtime_holdings_value"]=holdings
        out["inferred_ending_holdings_value"]=inferred
        out["ending_inferred_cash_from_original_runtime"]=end_equity-holdings
    out["ending_native_chart_equity"]=ending
    out["ending_original_report_equity"]=end_equity
    out["ending_native_chart_cash"]=rows[-1]["cash"]
    out["ending_native_chart_units"]=rows[-1]["units"]
    out["final_native_contributed_total"]=rows[-1]["contributed"]
    out["observational_cash_plus_holdings_reconciled"]=True
    return out


def project(original_json, diagnostic_json):
    """All original sessions required; no chart padding, truncation, or proxies."""
    original, frozen = extract(original_json)  # locks ORIGINAL SHA / daily identity
    rerun = compare_original_rerun_invariants(original_json, diagnostic_json)
    obj=json.loads(Path(diagnostic_json).read_bytes())
    try:
        series=obj["charts"][CHART]["series"]
    except (KeyError, TypeError) as exc:
        raise ValueError("LEAN_P1_PORTFOLIO_OBSERVER_CHART_MISSING") from exc
    if not isinstance(series,dict):
        raise ValueError("LEAN_P1_INVALID_SERIES")
    missing=[name for name in RAW_PLOTS if name not in series]
    if missing:
        raise ValueError("LEAN_P1_MISSING_SERIES:"+",".join(missing))
    n=len(original)
    streams={}
    for name in RAW_PLOTS:
        x=series[name].get("values")
        if not isinstance(x,list) or len(x)!=n:
            raise ValueError("LEAN_P1_INCOMPLETE_EXACT_DAILY_SERIES:"+name)
        streams[name]=x
    result=[]
    previous_contribution=None
    previous_units=None
    deposits=0
    first_mismatches=[]
    max_nav_error=0.
    for i,ref in enumerate(original):
        timestamps=[]
        obs={"date":ref["date"]}
        for name in RAW_PLOTS:
            point=streams[name][i]
            if not isinstance(point,(list,tuple)) or len(point)!=2:
                raise ValueError("LEAN_P1_INVALID_PLOT_POINT:"+name)
            try:
                ts=int(point[0])
            except (ValueError,TypeError,OverflowError) as exc:
                raise ValueError("LEAN_P1_INVALID_TIMESTAMP:"+name) from exc
            if ts != datetime.fromisoformat(ref["timestamp_utc"].replace("Z","+00:00")).timestamp():
                raise ValueError("LEAN_P1_TIMESTAMP_NOT_IDENTICAL_TO_ORIGINAL:"+name+":"+ref["date"])
            if datetime.fromtimestamp(ts, timezone.utc).date().isoformat()!=ref["date"]:
                raise ValueError("LEAN_P1_DATE_NOT_IDENTICAL_TO_ORIGINAL")
            timestamps.append(ts)
            obs[name]=_num(point[1],name)
        if len(set(timestamps))!=1:
            raise ValueError("LEAN_P1_INTERSERIES_TIMESTAMP_DRIFT")
        if obs["equity"]<=0 or obs["units"]<=0 or obs["contributed"]<=0:
            raise ValueError("LEAN_P1_IMPOSSIBLE_ACCOUNT_LEVEL")
        if obs["cash"] < -max(1.,obs["equity"]*1e-7):
            raise ValueError("LEAN_P1_NEGATIVE_CASH_WITHOUT_MARGIN")
        for k in ("qqq_quantity","qld_quantity","tqqq_quantity"):
            if obs[k]<-1e-6:
                raise ValueError("LEAN_P1_NEGATIVE_HOLDINGS_QUANTITY:"+k)
        obs["holdings_value"]=obs["equity"]-obs["cash"]
        if obs["holdings_value"] < -1e-5:
            raise ValueError("LEAN_P1_NEGATIVE_HOLDINGS_VALUE")
        nav=obs["equity"]/obs["units"]
        original_nav=ref["nav_multiple"]
        error=abs(nav-original_nav)
        max_nav_error=max(max_nav_error,error)
        if error>max(NAV_ABS_TOL,NAV_REL_TOL*abs(original_nav)):
            if len(first_mismatches)<10:
                first_mismatches.append({"date":ref["date"],
                  "chart_nav":original_nav,"p1_equity_div_units":nav,
                  "absolute_delta":error})
        if previous_contribution is None:
            if abs(obs["contributed"]-INITIAL_CAPITAL)>.5:
                raise ValueError("LEAN_P1_INITIAL_CASHFLOW_MISMATCH")
        else:
            delta=obs["contributed"]-previous_contribution
            if abs(delta)> .5 and abs(delta-MONTHLY_DEPOSIT)>.5:
                raise ValueError("LEAN_P1_NONMONTHLY_CASHFLOW_AMOUNT:"+ref["date"])
            if delta>.5:
                deposits+=1
                if previous_units is not None and obs["units"] < previous_units-max(.01,previous_units*1e-5):
                    raise ValueError("LEAN_P1_UNITS_DROPPED_ON_CONTRIBUTION")
        previous_contribution=obs["contributed"]
        previous_units=obs["units"]
        result.append(obs)
    if first_mismatches:
        raise ValueError("LEAN_P1_NAV_UNITS_DO_NOT_RECONCILE_TO_ORIGINAL:"+str(first_mismatches[:2]))
    if deposits!=EXPECTED_DEPOSITS or abs(result[-1]["contributed"]-EXPECTED_CONTRIBUTED)>.5:
        raise ValueError("LEAN_P1_CASHFLOW_LIFECYCLE_MISMATCH")
    endpoint=_pct_stats(result,original_json)
    audit={
        "status":"ORIGINAL_LEAN_P1_OBSERVED_CHART_RECONCILED",
        "source_original_sha256":frozen["source_sha256"],
        "source_observer_sha256":hashlib.sha256(Path(diagnostic_json).read_bytes()).hexdigest(),
        "native_replay_invariants":rerun,
        "rows":len(result),
        "fields":list(COLUMNS),
        "chart_p1_ledger_not_independent_broker_feed":True,
        "all_original_chart_timestamps_reconciled":True,
        "original_sl724_NAV_vs_equity_units_max_absolute_error":max_nav_error,
        "NAV_quantization_abs_tolerance":NAV_ABS_TOL,
        "NAV_quantization_rel_tolerance":NAV_REL_TOL,
        "contribution_count":deposits,
        "monthly_contribution_USD":MONTHLY_DEPOSIT,
        "cumulative_contributed_USD":result[-1]["contributed"],
        "endpoint_reconciliation":endpoint,
        "native_plot_values_bit_exact_unrounded":False,
        "lean_native_portfolio_evidence_available":True,
        "independently_reconstructed_Python_same_start_portfolio_path":False,
        "full_portfolio_path_PARITY_proven":False,
        "independent_09_31_09_32_NBBO_proven":False,
        "actual_broker_fills_proven":False,
        "capital_deployment_authorized":False,
        "no_user_private_raw_run_data_published":True,
        "limit":"Validates 7 complete native LEAN end-of-day portfolio chart series, contribution lifecycle and originally locked metrics. Plot quantization prevents bit-level exact portfolio-path claims. Cross-provider Python NAV path remains a separate missing evidence layer."
    }
    return result,audit


def export_private(original_json,diagnostic_json,out=DEFAULT_CSV,audit_out=DEFAULT_AUDIT):
    rows,audit=project(original_json,diagnostic_json)
    out=Path(out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)
    audit["private_portfolio_csv_sha256"]=hashlib.sha256(out.read_bytes()).hexdigest()
    write_json_atomic(audit_out,audit)
    return audit


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--original",required=True,help="PRIVATE locked original native QC results")
    p.add_argument("--diagnostic",required=True,help="PRIVATE P1 portfolio chart QC observer results")
    p.add_argument("--out-private-csv",default=str(DEFAULT_CSV))
    p.add_argument("--audit-private-json",default=str(DEFAULT_AUDIT))
    args=p.parse_args()
    report=export_private(args.original,args.diagnostic,args.out_private_csv,args.audit_private_json)
    print(json.dumps({
        "status":report["status"],
        "rows":report["rows"],
        "contributions":report["contribution_count"],
        "native_portfolio_observed":report["lean_native_portfolio_evidence_available"],
        "independent_broker_quotes_proven":False,
        "capital_deployment_authorized":False,
        "private_audit_path":args.audit_private_json
    },indent=2))


if __name__=="__main__":
    main()

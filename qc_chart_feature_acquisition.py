"""Recover original LEAN diagnostic features from FREE backtest Download Results.

Requires: original frozen SL724 results JSON and separate observer-instrumented
LEAN diagnostic run. Compare exact original leverage state by state first.
Chart precision and native provenance limitations remain explicitly disclosed.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path

from qc_original_lean_chart_audit import extract
from qc_input_ingestion import validate_export

CHART="SL724_P0_FEATURES"
FEATURES=("close","sma50","sma200","vol20","mom12","level","defense")
FIELDS=("date",)+FEATURES+("leverage",)


def day(ts):
    return datetime.fromtimestamp(int(ts),timezone.utc).date().isoformat()


def project(original_json, diagnostic_json):
    original,audit=extract(original_json)
    diagnostic_bytes=Path(diagnostic_json).read_bytes()
    diagnostic=json.loads(diagnostic_bytes)
    charts=diagnostic["charts"]
    raw_feature_series=charts[CHART]["series"]
    raw_leverage=charts["SL724"]["series"]["Leverage"]["values"]
    if any(col not in raw_feature_series for col in FEATURES):
        raise ValueError("LEAN_DIAGNOSTIC_FEATURE_SERIES_MISSING")
    series={col:raw_feature_series[col]["values"] for col in FEATURES}
    n=len(original)
    if len(raw_leverage)!=n:
        raise ValueError("LEAN_DIAGNOSTIC_CHART_TRUNCATED_OR_WRONG_SESSION_COUNT")
    lengths={key:len(series[key]) for key in FEATURES}
    if len(set(lengths.values()))!=1 or next(iter(lengths.values())) not in (n,n+1):
        raise ValueError("LEAN_DIAGNOSTIC_CHART_TRUNCATED_OR_WRONG_SESSION_COUNT")
    extra_days=next(iter(lengths.values()))-n
    trailing=None
    if extra_days:
        # Only one real XNYS session AFTER the immutable original decision
        # range may be excluded; never truncate mismatches within the range.
        import exchange_calendars as xcals
        cal=xcals.get_calendar("XNYS")
        last=cal.date_to_session(original[-1]["date"])
        expected_extra=str(cal.next_session(last).date())
        actual_extra={key:day(series[key][n][0]) for key in FEATURES}
        if len(set(actual_extra.values()))!=1 or set(actual_extra.values())!={expected_extra}:
            raise ValueError("LEAN_DIAGNOSTIC_UNEXPECTED_TRAILING_SESSION")
        trailing=expected_extra
    result=[]; first_errors=[]
    for i,expected in enumerate(original):
        observed=expected["date"]
        for key in FEATURES:
            point=series[key][i]
            if day(point[0])!=observed:
                raise ValueError("LEAN_DIAGNOSTIC_FEATURE_DATES_DO_NOT_MATCH_ORIGINAL:"+key+":"+observed)
        feature_instants={key:int(series[key][i][0]) for key in FEATURES}
        if len(set(feature_instants.values()))!=1:
            raise ValueError("LEAN_DIAGNOSTIC_FEATURE_TIMESTAMPS_NOT_SYNCHRONIZED")
        if day(raw_leverage[i][0])!=observed:
            raise ValueError("LEAN_DIAGNOSTIC_LEVERAGE_DATES_DO_NOT_MATCH_ORIGINAL")
        lev=float(raw_leverage[i][1])
        if not math.isfinite(lev) or lev!=expected["leverage"]:
            first_errors.append({"date":observed,"original":expected["leverage"],"diagnostic":lev})
            if len(first_errors)>=20:
                break
        values={k:float(series[k][i][1]) for k in FEATURES}
        if any(not math.isfinite(x) for x in values.values()):
            raise ValueError("LEAN_DIAGNOSTIC_NONFINITE_FEATURE")
        level=values["level"]
        defense=values["defense"]
        if level not in (1,2,3) or defense not in (0,1):
            raise ValueError("LEAN_DIAGNOSTIC_ILLEGAL_LEVEL_OR_DEFENSE")
        result.append({
            "date":observed,
            "close":format(values["close"],".17g"),
            "sma50":format(values["sma50"],".17g"),
            "sma200":format(values["sma200"],".17g"),
            "vol20":format(values["vol20"],".17g"),
            "mom12":format(values["mom12"],".17g"),
            "level":str(int(level)),
            "defense":"true" if int(defense) else "false",
            "leverage":format(lev,".17g"),
        })
    if first_errors:
        raise ValueError("LEAN_DIAGNOSTIC_CHANGED_FROZEN_LEVERAGE:"+json.dumps(first_errors))
    if len(result)!=n:
        raise ValueError("LEAN_DIAGNOSTIC_INCOMPLETE_ORIGINAL_ALIGNMENT")
    return result, {
        "status":"CHART_TRANSPORT_EXTRACTED_NOT_SOURCE_AUTHENTICATED",
        "original_source_sha256":audit["source_sha256"],
        "diagnostic_result_sha256":hashlib.sha256(diagnostic_bytes).hexdigest(),
        "expected_sessions":n,
        "aligned_sessions":len(result),
        "diagnostic_series_sessions":n+extra_days,
        "excluded_trailing_feature_session":trailing,
        "excluded_trailing_sessions":extra_days,
        "all_original_sessions_compared_without_backfill":True,
        "frozen_leverage_aligned_to_original":True,
        "native_feature_serialization_exact_precision_proven":False,
        "native_algorithm_source_identity_proven":False,
        "automatic_model_promotion":False,
        "claim_boundary":"Original reference and diagnostic state align, but chart series may round features and original LEAN source-code identity is not independently attested.",
    }



def _compare_lean_orders_preserving_economics(reference_orders, rerun_orders):
    """Compare all native order fields with narrow JSON float serialization tolerance.

    Original P1 results may round LEAN's binary floating-point price, total
    value, and submission bid/ask/last from 16 to 15 decimal significant digits,
    while having IDENTICAL economic executions. Require exactly the same order
    IDs, status, direction, quantity, tags, timestamps, symbol, and structure.
    Only five numeric quote/price/value paths may use 1e-12 relative OR
    1e-13 absolute tolerance. This is far below a cent at normal order size,
    and cannot mask any real execution change. Broker realism NOT proven.
    """
    float_tol_rel=1e-12
    float_tol_abs=1e-13
    result={"matched":False,"expected_order_count":len(reference_orders),
            "observer_order_count":len(rerun_orders),
            "tolerated_numeric_field_count":0,
            "max_relative_difference_tolerated":0.,
            "max_absolute_difference_tolerated":0.,
            "all_discrete_order_attributes_identical":False,
            "orders_byte_identical":reference_orders==rerun_orders}
    if not isinstance(reference_orders,dict) or not isinstance(rerun_orders,dict):
        raise ValueError("LEAN_DIAGNOSTIC_ORDER_FORMAT_INVALID")
    if set(reference_orders)!=set(rerun_orders):
        return result
    permitted={"price","value"}
    quotes={"bidPrice","askPrice","lastPrice"}
    def equivalent_float(a,b):
        if (type(a) not in (int,float) or type(b) not in (int,float)
            or not (math.isfinite(a) and math.isfinite(b))):
            return False
        if not math.isclose(a,b,rel_tol=float_tol_rel,abs_tol=float_tol_abs):
            return False
        if a!=b:
            result["tolerated_numeric_field_count"]+=1
            result["max_absolute_difference_tolerated"]=max(
                result["max_absolute_difference_tolerated"],abs(a-b))
            result["max_relative_difference_tolerated"]=max(
                result["max_relative_difference_tolerated"],
                abs(a-b)/max(abs(a),abs(b),1e-100))
        return True
    for oid in reference_orders:
        a,b=reference_orders[oid],rerun_orders[oid]
        if not (isinstance(a,dict) and isinstance(b,dict)
                and set(a)==set(b)):
            return result
        for name in a:
            if name in permitted:
                if not equivalent_float(a[name],b[name]):
                    return result
            elif name=="orderSubmissionData":
                qa,qb=a[name],b[name]
                if qa is None or qb is None:
                    if qa!=qb:return result
                    continue
                if not (isinstance(qa,dict) and isinstance(qb,dict)
                        and set(qa)==set(qb)):
                    return result
                for field in qa:
                    if field in quotes:
                        if not equivalent_float(qa[field],qb[field]):
                            return result
                    elif qa[field]!=qb[field]:
                        return result
            elif a[name]!=b[name]:
                return result
    result["matched"]=True
    result["all_discrete_order_attributes_identical"]=True
    return result


def compare_original_rerun_invariants(original_json, diagnostic_json):
    """Locked reference execution economics, with strict numeric transport tolerance.

    Both private JSONs stay private. Rounded float JSON transport is not
    evidence of a new fill when identical economically. Any discrete order,
    trade, strategy chart or statistics mutation rejects the observer rerun.
    """
    reference=json.loads(Path(original_json).read_bytes())
    rerun=json.loads(Path(diagnostic_json).read_bytes())
    locked=("orders","statistics","runtimeStatistics","profitLoss","rollingWindow")
    if any(name not in reference or name not in rerun for name in locked):
        raise ValueError("LEAN_MISSING_ORIGINAL_RUN_INVARIANT_FIELD")
    order_audit=_compare_lean_orders_preserving_economics(
        reference["orders"],rerun["orders"])
    equal={"orders":order_audit["matched"]}
    equal.update({name:reference[name]==rerun[name] for name in locked if name!="orders"})
    equal["native_sl724_leverage_nav_drawdown"]=(
        reference.get("charts",{}).get("SL724",{}).get("series")==
        rerun.get("charts",{}).get("SL724",{}).get("series"))
    left=reference.get("totalPerformance",{})
    right=rerun.get("totalPerformance",{})
    if not isinstance(left,dict) or not isinstance(right,dict):
        raise ValueError("LEAN_INVALID_TRADE_SUMMARY")
    original_trades=left.get("closedTrades")
    new_trades=right.get("closedTrades")
    if not isinstance(original_trades,list) or not isinstance(new_trades,list):
        raise ValueError("LEAN_MISSING_CLOSED_TRADE_DETAILS")
    strip_uuid=lambda rows:[{k:v for k,v in row.items() if k!="id"} for row in rows]
    equal["closed_trade_economics_excluding_generated_uuid"]=(
        strip_uuid(original_trades)==strip_uuid(new_trades))
    if not all(equal.values()):
        raise ValueError("LEAN_DIAGNOSTIC_CHANGED_ORIGINAL_RUN:"+json.dumps(
            [name for name,matched in equal.items() if not matched]))
    return {"frozen_reference_order_count":len(reference["orders"]),
            "native_lean_closed_trades":len(original_trades),
            "unchanged_fields":equal,
            "native_order_numeric_transport_audit":order_audit,
            "native_execution_behavior_unchanged":True,
            "original_run_source_code_hash_attested":False,
            "independent_broker_quotes_proven":False}



def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--original",required=True)
    parser.add_argument("--diagnostic",required=True)
    parser.add_argument("--out",default="governance/qc_lean_daily_features.csv")
    parser.add_argument("--audit",default="research/local/lean_chart_transport_audit.json")
    args=parser.parse_args()
    original_run_audit=compare_original_rerun_invariants(args.original,args.diagnostic)
    rows,report=project(args.original,args.diagnostic)
    report["original_run_invariants"]=original_run_audit
    out=Path(args.out);out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();w.writerows(rows)
    gate=validate_export(out)
    report["structural_input_gate"]=gate
    report["feature_csv_sha256"]=hashlib.sha256(out.read_bytes()).hexdigest()
    path=Path(args.audit);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(report,indent=2))
    if gate["status"]!="VALID":
        raise RuntimeError("FROZEN_LEAN_DIAGNOSTIC_INPUT_NOT_ACCEPTED")


if __name__=="__main__":
    main()

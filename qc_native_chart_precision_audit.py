"""Conservative P0 chart-precision decision stability audit (NOT source proof).

Every pre-observed LEAN chart feature CSV remains PRIVATE and is validated
against pinned 3,774 original session dates, daily states and 67 transitions.
The assumed maximum chart numeric perturbations below are hypothetical
absolute error bounds, not independently measured plot encoder tolerances.

If every relevant inequality exceeds its worst-case perturbation, then each
historical decision is invariant under that assumed bounded chart error
(conditional inductive claim), not necessarily bit-exact original indicator
provenance, real broker fills, or independent risk-adjusted alpha.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from qc_input_ingestion import validate_export
from stocklens.core import Features,next_level,defense_active,LEVEL_LEVERAGE
from json_artifacts import write_json_atomic

EPS = {"close":1e-4,"sma50":1e-4,"sma200":1e-4,
       "vol20":1e-6,"mom12":1e-6}
VOL_LEVELS=(.28,.32,.38,.42)
DEFAULT_PRIVATE_FILE=Path("research/local/qc_lean_daily_features_PRIVATE.csv")
DEFAULT_AUDIT=Path("research/local/qc_chart_precision_audit_PRIVATE.json")


def _num(value,name):
    try: f=float(value)
    except (ValueError,TypeError,OverflowError) as e:
        raise ValueError("INVALID_CHARTED_FEATURE:"+name) from e
    if not math.isfinite(f):
        raise ValueError("INVALID_CHARTED_FEATURE:"+name)
    return f


def evaluate(rows,*,validated_original_session_identity=False,assumed_abs_error=EPS):
    if not rows:
        raise ValueError("NO_CHARTED_NATIVE_FEATURE_ROWS")
    errs=dict(assumed_abs_error)
    if set(errs)!=set(EPS) or any(
        not math.isfinite(e) or e<=0 for e in errs.values()
    ):
        raise ValueError("INVALID_ASSUMED_PLOT_ERROR_ENVELOPE")
    min_abs={"trend":float("inf"),"sma50_sma200":float("inf"),
             "momentum_zero":float("inf"),"volatility_threshold":float("inf")}
    critical={}
    fragile=[]
    mismatch=[]
    last_day=""
    previous_level=None
    for row in rows:
        day=row["date"]
        if not isinstance(day,str) or day<=last_day:
            raise ValueError("UNSORTED_DUPLICATE_FEATURE_DATES")
        last_day=day
        f=Features(**{k:_num(row[k],k) for k in EPS})
        if min(f.close,f.sma50,f.sma200)<=0 or f.vol20<0:
            raise ValueError("INVALID_CHARTED_FEATURE_RANGE")
        prev=previous_level if previous_level is not None else 1
        trend_factor=.99 if prev>1 else 1.01
        trend_raw=abs(f.close-trend_factor*f.sma200)
        dists={
            "trend":trend_raw-(errs["close"]+trend_factor*errs["sma200"]),
            "sma50_sma200":abs(f.sma50-f.sma200)-(errs["sma50"]+errs["sma200"]),
            "momentum_zero":abs(f.mom12)-errs["mom12"],
            "volatility_threshold":min(abs(f.vol20-cut) for cut in VOL_LEVELS)-errs["vol20"],
        }
        for name,m in dists.items():
            if m<min_abs[name]:
                min_abs[name]=m
                critical[name]=day
            if m<=0 and len(fragile)<20:
                fragile.append({"date":day,"condition":name,
                                "assumed_error_remaining":m})
        calc=next_level(f,previous_level)
        protection=defense_active(f)
        exposure=0. if protection else LEVEL_LEVERAGE[calc]
        observed_level=int(row["level"])
        observed_defense=str(row["defense"]).strip().lower()=="true"
        observed_exposure=_num(row["leverage"],"leverage")
        if (calc!=observed_level or protection!=observed_defense or
            exposure!=observed_exposure):
            if len(mismatch)<20:
                mismatch.append({"date":day,"calculated_level":calc,
                                 "observed_level":observed_level})
        previous_level=calc
    return {
        "kind":"ORIGINAL_LEAN_P0_CHART_ROUNDING_BOUNDED_STABILITY_AUDIT",
        "status":"BOUND_STABLE_ON_CHARTED_VALUES" if not mismatch and not fragile else
                 "CHARTED_VALUE_COMPUTATION_MISMATCH" if mismatch else
                 "BOUND_COULD_FLIP_DECISION",
        "compared_sessions":len(rows),
        "observed_state_mathematical_matches":len(rows)-len(mismatch),
        "mismatch_first20":mismatch,
        "fragile_sessions_first20":fragile,
        "critical_day_by_condition":critical,
        "minimum_distance_after_assumed_perturbation_absolute_units":min_abs,
        "assumed_max_absolute_chart_error":errs,
        "conditionally_robust_if_true_plot_error_within_assumed_bounds":not fragile and not mismatch,
        "immutable_original_session_state_verified":validated_original_session_identity,
        "original_unrounded_LEAN_indicator_bits_attested":False,
        "actual_plot_encoder_error_bound_independently_verified":False,
        "public_release_of_user_native_feature_csv_authorized":False,
        "portfolio_path_PARITY_proven":False,
        "live_broker_fills_proven":False,
        "capital_deployment_authorized":False,
        "claim_boundary":"A stability theorem conditional on user-chosen chart error bounds. It is NOT empirical quantization validation or true native source provenance."
    }


def audit(path=DEFAULT_PRIVATE_FILE,*,out=DEFAULT_AUDIT):
    checked=validate_export(path=path)
    if checked["status"]!="VALID":
        raise ValueError("PINNED_ORIGINAL_LEAN_INPUT_VALIDATION_FAILED:"+
                         ",".join(checked.get("errors",[])))
    with Path(path).open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    r=evaluate(rows,validated_original_session_identity=True)
    r["input_canonical_sha256"]=checked["sha256"]
    r["input_original_calendar_and_states_validation"]=checked["checks"]
    r["source_authenticity_proven"]=False
    write_json_atomic(out,r)
    return r


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--native-private-csv",default=str(DEFAULT_PRIVATE_FILE))
    p.add_argument("--out-private-json",default=str(DEFAULT_AUDIT))
    args=p.parse_args()
    result=audit(args.native_private_csv,out=args.out_private_json)
    print(json.dumps({
        "status":result["status"],"rows":result["compared_sessions"],
        "fragile_first20":len(result["fragile_sessions_first20"]),
        "smallest_residual_margin":result["minimum_distance_after_assumed_perturbation_absolute_units"],
        "original_unrounded_bits_attested":False,
        "capital_deployment_authorized":False,
    },indent=2))


if __name__=="__main__":
    main()

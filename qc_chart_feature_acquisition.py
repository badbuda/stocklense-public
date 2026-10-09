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
    if len(raw_leverage)!=n or any(len(series[key])!=n for key in FEATURES):
        raise ValueError("LEAN_DIAGNOSTIC_CHART_TRUNCATED_OR_WRONG_SESSION_COUNT")
    result=[]; first_errors=[]
    for i,expected in enumerate(original):
        observed=expected["date"]
        for key in FEATURES:
            point=series[key][i]
            if day(point[0])!=observed:
                raise ValueError("LEAN_DIAGNOSTIC_FEATURE_DATES_DO_NOT_MATCH_ORIGINAL:"+key+":"+observed)
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
        "frozen_leverage_aligned_to_original":True,
        "native_feature_serialization_exact_precision_proven":False,
        "native_algorithm_source_identity_proven":False,
        "automatic_model_promotion":False,
        "claim_boundary":"Original reference and diagnostic state align, but chart series may round features and original LEAN source-code identity is not independently attested.",
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--original",required=True)
    parser.add_argument("--diagnostic",required=True)
    parser.add_argument("--out",default="governance/qc_lean_daily_features.csv")
    parser.add_argument("--audit",default="research/local/lean_chart_transport_audit.json")
    args=parser.parse_args()
    rows,report=project(args.original,args.diagnostic)
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

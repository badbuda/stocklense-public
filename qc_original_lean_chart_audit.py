"""Auditable extraction of real daily LEAN 7.24 SL724 charts.

Consumes the user's ORIGINAL QuantConnect 'Download Results' JSON locally.
Does not download market data, infer features from Yahoo, alter trading code,
or publish sensitive raw results. Requires locked source SHA-256 by default.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from qc_input_ingestion import transition_hash

ORIGINAL_SOURCE_SHA256 = "65cb291e6552dc0f86b32106bc3fe3f7a7ed8a127b3d0d6f84a60a8f5800b6f7"
TRANSITIONS = Path("governance/qc_724_leverage_transitions.json")
MANIFEST = Path("governance/qc_724_daily_state_manifest.json")
COLUMNS = ("date", "timestamp_utc", "leverage", "nav_multiple", "drawdown_pct")


def extract(original_json, *, expected_source_sha=ORIGINAL_SOURCE_SHA256,
            manifest=MANIFEST, golden=TRANSITIONS):
    original=Path(original_json).read_bytes()
    sha=hashlib.sha256(original).hexdigest()
    if expected_source_sha and sha != expected_source_sha:
        raise ValueError("ORIGINAL_QUANTCONNECT_SOURCE_SHA256_MISMATCH")
    source=json.loads(original)
    series=source["charts"]["SL724"]["series"]
    raw={name:series[name]["values"] for name in ("Leverage","NAV","Drawdown")}
    n=len(raw["Leverage"])
    if n==0 or any(len(v)!=n for v in raw.values()):
        raise ValueError("SL724_SERIES_LENGTH_MISMATCH")
    m=json.loads(Path(manifest).read_text(encoding="utf-8"))
    ref=json.loads(Path(golden).read_text(encoding="utf-8"))
    if n!=m["sessions"] or n!=ref["sessions"]:
        raise ValueError("LEAN_REFERENCE_SESSIONS_MISMATCH")
    rows=[];transitions=[];counts=Counter();last=None
    for i in range(n):
        timestamps=[int(raw[key][i][0]) for key in ("Leverage","NAV","Drawdown")]
        if len(set(timestamps))!=1:
            raise ValueError("SL724_SESSION_TIMESTAMPS_NOT_ALIGNED")
        ts=datetime.fromtimestamp(timestamps[0],timezone.utc)
        day=ts.date().isoformat()
        lev=float(raw["Leverage"][i][1])
        nav=float(raw["NAV"][i][1])
        draw=float(raw["Drawdown"][i][1])
        if lev not in (0,1.25,2,3) or nav<=0 or not (-100<=draw<=0):
            raise ValueError("SL724_INVALID_OBSERVED_STATE")
        if rows and day<=rows[-1]["date"]:
            raise ValueError("SL724_UNORDERED_OR_DUPLICATE_SESSION")
        if last is None or lev!=last:
            transitions.append([day,int(lev) if lev.is_integer() else lev])
        last=lev
        counts[str(lev)]+=1
        rows.append({"date":day,"timestamp_utc":ts.isoformat().replace("+00:00","Z"),
                     "leverage":lev,"nav_multiple":nav,"drawdown_pct":draw})
    assert len(rows)==n
    if rows[0]["timestamp_utc"]!=m["first_time_utc"] or rows[-1]["timestamp_utc"]!=m["last_time_utc"]:
        raise ValueError("SL724_ORIGINAL_TIME_BOUNDARY_MISMATCH")
    if transitions!=ref["transitions"] or transition_hash(transitions)!=ref["transition_sha256"]:
        raise ValueError("SL724_ORIGINAL_TRANSITIONS_DRIFT")
    expected={str(float(k)):v for k,v in m["leverage_counts"].items()}
    if dict(counts)!=expected:
        raise ValueError("SL724_ORIGINAL_LEVERAGE_DISTRIBUTION_DRIFT")
    if abs(min(r["drawdown_pct"] for r in rows)-m["max_drawdown_pct"])>1e-8:
        raise ValueError("SL724_ORIGINAL_DRAWDOWN_DRIFT")
    if abs(rows[-1]["nav_multiple"]-m["last_nav_multiple"])>1e-9:
        raise ValueError("SL724_ORIGINAL_NAV_DRIFT")
    return rows,{
        "status":"VERIFIED_ORIGINAL_LEAN_CHART",
        "kind":"LEAN_SL724_DAILY_CHART_SOURCE_VERIFIED",
        "source_sha256":sha,"sessions":n,
        "first_date":rows[0]["date"],"last_date":rows[-1]["date"],
        "transition_count":len(transitions),
        "transition_sha256":transition_hash(transitions),
        "leverage_counts":dict(counts),
        "final_nav_multiple":rows[-1]["nav_multiple"],
        "max_drawdown_pct":min(r["drawdown_pct"] for r in rows),
        "contains_daily_indicators":False,
        "same_input_parity_proven":False,
        "claim_boundary":"Only original chart states/leverage/NAV/drawdown are proven. No daily LEAN close/SMA/vol/momentum or same-input Python parity is inferred.",
    }


def compare_original_vs_execution_proxy(original, proxy):
    """Research-only: effective leverage in modeled daily-open fills is NOT a LEAN decision."""
    proxy_rows=proxy.get("daily",[])
    by_date={r["date"]:r for r in proxy_rows}
    matches=total=0
    samples=[]
    for row in original:
        other=by_date.get(row["date"])
        if other is None:
            continue
        total+=1
        good=abs(row["leverage"]-float(other["l"]))<1e-12
        matches+=int(good)
        if not good and len(samples)<15:
            samples.append({"date":row["date"],"lean_leverage":row["leverage"],
                            "modeled_prior_signal_open_exposure":other["l"],
                            "model_signal_date":other.get("signal")})
    return {"scope":"CROSS_PROVIDER_DECISION_VS_PRIOR_SIGNAL_OPEN_EXPOSURE_DIAGNOSTIC_ONLY",
            "overlap_sessions":total,"matching_exposures":matches,
            "match_rate":matches/total if total else None,
            "first_differences":samples,"same_input_parity_proven":False,
            "warning":"Uses different providers and may compare LEAN decision dates with next-open prior-day exposures. Neither disagreements nor agreements prove model identity."}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-json",required=True,help="private ORIGINAL Determined Red Orange Duck.json")
    p.add_argument("--output-csv",default="research/local/lean_original_daily_chart.csv")
    p.add_argument("--audit-json",default="research/local/lean_original_daily_audit.json")
    p.add_argument("--proxy-json",help="Optional docs/portal-history.json for cross-provider diagnostics")
    args=p.parse_args()
    rows,audit=extract(args.source_json)
    csv_file=Path(args.output_csv);csv_file.parent.mkdir(parents=True,exist_ok=True)
    with csv_file.open("w",newline="",encoding="utf-8") as f:
        writer=csv.DictWriter(f,fieldnames=COLUMNS);writer.writeheader();writer.writerows(rows)
    audit["extracted_csv_sha256"]=hashlib.sha256(csv_file.read_bytes()).hexdigest()
    if args.proxy_json:
        audit["cross_provider"]=compare_original_vs_execution_proxy(
            rows,json.loads(Path(args.proxy_json).read_text(encoding="utf-8")))
    dest=Path(args.audit_json);dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_text(json.dumps(audit,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(audit,indent=2))


if __name__=="__main__":
    main()

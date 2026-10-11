"""SL9-022: Preserve original SL9-007 dates but NEVER call proxy rows live evidence.

No historical rewriting, no guessed first-seen timestamp, no orders.
"""
from __future__ import annotations
import csv
import io
import json
import math
from pathlib import Path

EID="SL9-007-UPSHIFT-CONFIRMATION"
LEDGER=Path("research/prospective/SL9-007-UPSHIFT-CONFIRMATION.csv")
REG=Path("research/prospective/registry.json")
GIT=Path("research/evidence/SL9-020-GIT-APPEARANCE.json")
ADAPTER=Path("research_data_adapter.py")
CHALLENGER=Path("research_upshift_confirmation.py")
OUT=Path("research/results/sl9_022_original_forward_qualification.json")
METADATA=Path("research/evidence/SL9-022-ORIGINAL-FORWARD-QUALIFICATION.json")
FIELDS=("asof_date","strategy_return","baseline_return","strategy_exposure","baseline_exposure")
EPS=1e-12


def audit(csv_bytes, registry, history, adapter_source, challenger_source):
    if not isinstance(csv_bytes,bytes):
        raise ValueError("ORIGINAL_SL9_007_CSV_BYTES_REQUIRED")
    raw=csv_bytes.decode("utf-8")
    source=list(csv.DictReader(io.StringIO(raw)))
    if len(source)!=10 or list(source[0])!=list(FIELDS):
        raise ValueError("SL9_007_ORIGINAL_COHORT_CHANGED")
    days=[z["asof_date"] for z in source]
    if days!=sorted(set(days)) or (days[0],days[-1])!=("2026-09-28","2026-10-09"):
        raise ValueError("SL9_007_COHORT_CALENDAR_CHANGED")
    registry_items=[z for z in registry.get("candidates",[]) if z.get("experiment_id")==EID]
    audits=[z for z in registry.get("last_ingestion_audit",[]) if z.get("experiment_id")==EID]
    if len(registry_items)!=1 or len(audits)!=1:
        raise ValueError("SL9_007_REGISTRATION_MISSING")
    a=audits[0]
    if (a.get("persisted_prospective_rows")!=10 or
        a.get("definition_matches_registration") is not True or
        a.get("fingerprint_matches_registration") is not False):
        raise ValueError("SL9_007_LINEAGE_NOT_SAME_AS_PREVIOUS_AUDIT")
    if ("qret*lev" not in adapter_source or "q*candidate" not in challenger_source
            or "baseline_return" not in adapter_source):
        raise ValueError("SL9_007_RETURN_SOURCE_CHANGED")
    if (history.get("experiment_id")!=EID or
        history.get("independently_verified_first_seen") is not False or
        len(history.get("snapshots",[]))!=3 or
        history["snapshots"][-1].get("dates")!=days):
        raise ValueError("SL9_007_GIT_APPEARANCE_CONTRACT_CHANGED")
    decisive=0
    largest=0.
    exposure_diffs=0
    details=[]
    for z in source:
        values=[]
        for k in FIELDS[1:]:
            v=float(z[k])
            if not math.isfinite(v):raise ValueError("SL9_007_NONFINITE_RETURN_OR_EXPOSURE")
            values.append(v)
        sr,br,se,be=values
        dr=abs(sr-br);de=abs(se-be)
        largest=max(largest,dr)
        is_decisive=dr>EPS or de>EPS
        decisive+=int(is_decisive)
        exposure_diffs+=int(de>EPS)
        details.append({"session_date":z["asof_date"],
                        "economically_distinguishing":is_decisive,
                        "historical_git_first_seen_verified":False,
                        "actual_observed_tqqq_ledger_replay":False})
    rows_before=len(history["snapshots"][0]["dates"])
    if rows_before!=8:raise ValueError("SL9_007_EARLIEST_GIT_SNAPSHOT_CHANGED")
    return {"schema_version":1,"experiment_id":EID,
        "status":"BLOCKED_PROXY_HISTORY_NO_QUALIFIED_FORWARD",
        "original_rows_preserved":len(source),
        "earliest_repo_git_snapshot_rows":rows_before,
        "economically_distinguishing_sessions":decisive,
        "exposure_distinguishing_sessions":exposure_diffs,
        "max_abs_return_difference":largest,
        "comparator_tolerance":EPS,
        "independently_verified_forward_observed_real_etf_sessions":0,
        "qualified_forward_paired_sessions":0,
        "return_basis":"PROXY_NOT_ETF",
        "original_return_equation":"QQQ_ADJUSTED_CLOSE_RETURN_TIMES_LEVERAGE",
        "real_tqqq_in_original_return_calculation":False,
        "historical_first_seen_proven":False,
        "git_author_time_is_external_receipt":False,
        "evidence_fingerprint_reconciled":False,
        "registered_fingerprint":a.get("registered_fingerprint"),
        "queue_fingerprint":a.get("queue_fingerprint"),
        "proposed_63_session_review_not_statistical_alpha_proof":True,
        "future_original_cohort_rewrite_authorized":False,
        "frozen_stocklens8_changed":False,
        "live_broker_trading_authorized":False,
        "automatic_model_promotion":False,
        "source_session_details":details}


def build():
    result=audit(LEDGER.read_bytes(),json.loads(REG.read_text()),
         json.loads(GIT.read_text()),ADAPTER.read_text(),CHALLENGER.read_text())
    OUT.parent.mkdir(parents=True,exist_ok=True)
    METADATA.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    # Permanent short source-of-truth; no rewriting user-supplied historic CSV.
    summary={k:v for k,v in result.items() if k!="source_session_details"}
    METADATA.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n")
    print("STOCKLENS_SL9_022_PROSPECTIVE_QUALIFICATION="+json.dumps({
      k:result[k] for k in ("original_rows_preserved",
        "economically_distinguishing_sessions",
        "independently_verified_forward_observed_real_etf_sessions",
        "return_basis","status")},sort_keys=True))
    return result


if __name__=="__main__":
    build()

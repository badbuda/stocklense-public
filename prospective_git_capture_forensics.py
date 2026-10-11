"""SL9-020: Git appearance of SL9-007 rows is not true prospective capture.
Does not modify frozen 8.0 or any original ledgers.
"""
import csv, hashlib, io, json, math
from datetime import datetime, timezone
from pathlib import Path
import exchange_calendars as xcals

EXPERIMENT="SL9-007-UPSHIFT-CONFIRMATION"
CSV=Path("research/prospective/SL9-007-UPSHIFT-CONFIRMATION.csv")
EVIDENCE=Path("research/evidence/SL9-020-GIT-APPEARANCE.json")
OUT=Path("research/results/sl9_020_forward_git_audit.json")
REPORT=Path("research/reports/SL9-020_20261011_GIT_FIRST_APPEARANCE.md")

def blob_sha(content):
    return hashlib.sha1(b"blob "+str(len(content)).encode()+b"\0"+content).hexdigest()

def evaluate(csv_bytes, snapshots, reg, adapter, candidate):
    rows=list(csv.DictReader(io.StringIO(csv_bytes.decode())))
    days=[r.get("asof_date") for r in rows]
    expected=["asof_date","strategy_return","baseline_return","strategy_exposure","baseline_exposure"]
    if not rows or list(rows[0])!=expected or days!=sorted(set(days)):
        raise ValueError("FORWARD_LEDGER_SCHEMA_OR_DATES_INVALID")
    for row in rows:
        try:
            v=[float(row[k]) for k in expected[1:]]
            if not all(math.isfinite(x) for x in v): raise ValueError()
        except (TypeError,ValueError,KeyError):
            raise ValueError("FORWARD_NUMERIC_INVALID")
    if snapshots.get("schema_version")!=1 or snapshots.get("experiment_id")!=EXPERIMENT or snapshots.get("independently_verified_first_seen") is not False:
        raise ValueError("GIT_METADATA_NOT_INDEPENDENT_CAPTURE")
    history=snapshots.get("snapshots")
    if not isinstance(history,list) or len(history)!=3:
        raise ValueError("GIT_SNAPSHOT_LIST_INVALID")
    prev=set()
    first_seen={}
    last=None
    for snap in history:
        commit=snap.get("commit_sha","")
        source_sha=snap.get("git_blob_sha","")
        ds=snap.get("dates")
        t=datetime.fromisoformat(snap["author_date_utc"].replace("Z","+00:00"))
        if not (len(commit)==len(source_sha)==40 and t.utcoffset()==timezone.utc.utcoffset(t) and
                isinstance(ds,list) and ds==sorted(set(ds)) and set(ds)>prev and
                (last is None or t>last)):
            raise ValueError("GIT_SOURCE_HISTORY_INVALID")
        for day in set(ds)-prev:
            first_seen[day]={"session":day,"commit":commit,"git_author_time_utc":t.isoformat()}
        prev,last=set(ds),t
    if sorted(prev)!=days or blob_sha(csv_bytes)!=history[-1]["git_blob_sha"]:
        raise ValueError("GIT_LATEST_LEDGER_BLOB_MISMATCH")
    c=[x for x in reg.get("candidates",[]) if x.get("experiment_id")==EXPERIMENT]
    a=[x for x in reg.get("last_ingestion_audit",[]) if x.get("experiment_id")==EXPERIMENT]
    if len(c)!=1 or len(a)!=1 or len(rows)!=a[0].get("persisted_prospective_rows"):
        raise ValueError("FORWARD_REGISTRY_INCONSISTENT")
    if any(d<=c[0]["inception_date"] for d in days) or a[0].get("fingerprint_matches_registration") is not False or a[0].get("definition_matches_registration") is not True:
        raise ValueError("FORWARD_REGISTRATION_LINEAGE_CHANGED")
    if "qret*lev" not in adapter or "q*candidate" not in candidate:
        raise ValueError("FORWARD_APPROXIMATE_QQQ_LEVERAGE_BASIS_CHANGED")
    cal=xcals.get_calendar("XNYS")
    plausible,late=[],[]
    for d in days:
        if not cal.is_session(d): raise ValueError("FORWARD_NON_XNYS_DAY")
        t=datetime.fromisoformat(first_seen[d]["git_author_time_utc"])
        if cal.session_close(d).to_pydatetime()<=t<cal.session_open(cal.next_session(d)).to_pydatetime():
            plausible.append(first_seen[d])
        else: late.append(first_seen[d])
    return {
      "kind":"SL9_020_PROSPECTIVE_GIT_SOURCE_FORENSICS",
      "original_modelled_rows_retained":len(rows),
      "rows_in_first_repository_snapshot":len(history[0]["dates"]),
      "git_author_timing_plausible_rows_NOT_PROVEN":len(plausible),
      "git_author_timing_late_rows":len(late),
      "late_rows":late,
      "git_author_time_is_not_server_first_seen":True,
      "no_independent_provider_capture_receipts":True,
      "independently_verified_forward_trading_rows":0,
      "real_tqqq_used_in_source_return_calculation":False,
      "research_return_basis":"QQQ_CLOSE_TO_CLOSE_RETURN_TIMES_TARGET_EXPOSURE",
      "registry_definition_matches":True,
      "registry_evidence_fingerprint_matches":False,
      "original_csv_git_blob_sha":blob_sha(csv_bytes),
      "frozen_stocklens8_modified":False,
      "automatic_promotion":False,
      "capital_deployment_authorized":False,
      "status":"BLOCKED_INDEPENDENT_FORWARD_CAPTURE_NOT_PROVEN"
    }

def build():
    report=evaluate(CSV.read_bytes(),json.loads(EVIDENCE.read_text()),
      json.loads(Path("research/prospective/registry.json").read_text()),
      Path("research_data_adapter.py").read_text(),
      Path("research_upshift_confirmation.py").read_text())
    OUT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,indent=2,sort_keys=True)+"\n")
    REPORT.write_text(
       "# SL9-020 — Original forward source Git first appearance\n\n"
       "Repo SHA references are Git objects, NOT independent timestamped "
       "provider/collector capture receipts. Author dates are client-supplied.\n\n"
       f"- Original historic after-inception research rows: {report['original_modelled_rows_retained']}\n"
       f"- Rows already in earliest accessible Git snapshot: {report['rows_in_first_repository_snapshot']}\n"
       f"- Git author-time close-to-next-open plausible rows: {report['git_author_timing_plausible_rows_NOT_PROVEN']}\n"
       f"- Late first visible rows based on untrusted Git author times: {report['git_author_timing_late_rows']}\n"
       "- Independently qualified forward *real TQQQ trading* sessions: 0\n"
       "- Research source computes QQQ daily return * target leverage, not real TQQQ fills.\n"
       "- Registered definition matches; research evidence fingerprints diverge.\n"
       "Original ledger untouched. Require signed live capture and actual ETF "
       "execution / comparable source receipts before claiming forward evidence.\n")
    print("STOCKLENS_SL9_020_GIT_FORWARD_AUDIT="+json.dumps({k:report[k] for k in (
      "original_modelled_rows_retained","rows_in_first_repository_snapshot",
      "git_author_timing_plausible_rows_NOT_PROVEN","git_author_timing_late_rows",
      "independently_verified_forward_trading_rows","status")},sort_keys=True))
    return report

if __name__=="__main__":
    build()

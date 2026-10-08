from __future__ import annotations
import csv, json
from datetime import date
from pathlib import Path

def _rows(p: Path):
    if not p.exists() or p.stat().st_size == 0: return []
    with p.open(encoding="utf-8", newline="") as f: return list(csv.DictReader(f))

def build_health(out_path="shadow_history/health.json"):
    problems=[]; warnings=[]; info=[]
    latest=Path("shadow_history/latest.json")
    signals=Path("shadow_history/signals.csv")
    if not latest.exists(): problems.append("MISSING_LATEST_SIGNAL")
    if not signals.exists(): problems.append("MISSING_SIGNAL_INDEX")
    report=json.loads(latest.read_text()) if latest.exists() else {}
    rows=_rows(signals)
    if rows and report and rows[-1].get("asof_date") != report["latest"]["asof_date"]:
        problems.append("LATEST_SIGNAL_INDEX_MISMATCH")
    dates=[r.get("asof_date") for r in rows]
    if len(dates)!=len(set(dates)): problems.append("DUPLICATE_SIGNAL_SESSION")
    ledger=_rows(Path("paper_portfolio/ledger.csv"))
    sessions=[r.get("session_date") for r in ledger]
    if len(sessions)!=len(set(sessions)): problems.append("DUPLICATE_PAPER_SESSION")
    replay_summary=Path("historical_replay/summary.json")
    if replay_summary.exists() and report:
        replay=json.loads(replay_summary.read_text())
        signal_date=report.get("latest",{}).get("asof_date")
        replay_date=replay.get("last_date")
        if signal_date and replay_date and signal_date!=replay_date:
            problems.append(f"STALE_SIGNAL_VS_REPLAY:{signal_date}!={replay_date}")
    else:
        info.append("FRESHNESS_REFERENCE_UNAVAILABLE")
    anomaly_path=Path("shadow_history/anomalies.json")
    if anomaly_path.exists():
        anomaly=json.loads(anomaly_path.read_text())
        if anomaly.get("status")=="BLOCK": problems.append("FEATURE_ANOMALY_BLOCK")
    else: problems.append("MISSING_ANOMALY_REPORT")
    revisions=_rows(Path("shadow_history/revision_audit.csv"))
    if revisions: info.append(f"NONMATERIAL_INPUT_REVISIONS:{len(revisions)}")
    status="RED" if problems else ("WARNING" if warnings else "GREEN")
    result={"status":status,"problems":problems,"warnings":warnings,"info":info,
            "signal_rows":len(rows),"paper_sessions":len(ledger),
            "asof_date": report.get("latest",{}).get("asof_date")}
    p=Path(out_path); p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,indent=2)+"\n")
    return result

if __name__=="__main__":
    print(json.dumps(build_health(),indent=2))

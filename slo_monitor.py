from __future__ import annotations
import csv,json
from pathlib import Path

def build_slo(out="shadow_history/slo.json", latest_path="output/latest_signal.json"):
    p=Path("shadow_history/signals.csv");rows=list(csv.DictReader(p.open())) if p.exists() else []
    dates=[r.get("asof_date") for r in rows if r.get("asof_date")];unique=len(set(dates))
    latest={}
    q=Path(latest_path)
    if q.exists():latest=json.loads(q.read_text())
    canonical=(latest.get("latest") or {}).get("asof_date")
    persisted=max(dates) if dates else None
    stale=bool(canonical and persisted and persisted<canonical)
    result={"signal_sessions_recorded":unique,"duplicate_signal_sessions":max(0,len(rows)-unique),"latest_canonical_completed_session":canonical,"latest_persisted_signal_session":persisted,"stale_vs_canonical_completed_session":stale,"target":"one immutable validated signal per canonical completed market session","status":"FAIL" if len(rows)!=unique or stale else "PASS"}
    q=Path(out);q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build_slo(),indent=2))

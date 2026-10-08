from __future__ import annotations
import json
from pathlib import Path
def build_data_provenance(out="shadow_history/data_provenance.json"):
    p=Path("output/latest_signal.json")
    if not p.exists(): r={"status":"MISSING_SIGNAL"}
    else:
        s=json.loads(p.read_text());a=s.get("data_audit",{})
        r={"status":"COMPLETE" if a.get("source") and a.get("feature_window_sha256") else "PARTIAL","source":a.get("source"),
           "raw_rows":a.get("raw_rows") or a.get("rows"),"completed_rows":a.get("completed_rows"),"last_completed_date":a.get("last_completed_date"),
           "feature_window_sessions":a.get("feature_window_sessions"),"feature_window_sha256":a.get("feature_window_sha256"),
           "dropped_incomplete_current_session":a.get("dropped_incomplete_current_session")}
    q=Path(out);q.parent.mkdir(parents=True,exist_ok=True);q.write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build_data_provenance(),indent=2))

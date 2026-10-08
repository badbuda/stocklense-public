from __future__ import annotations
import json
from pathlib import Path
def build_recovery_plan(out="shadow_history/recovery_plan.json"):
    def j(p,d=None):
        q=Path(p);return json.loads(q.read_text()) if q.exists() else (d or {})
    h=j("shadow_history/health.json");a=j("shadow_history/anomalies.json")
    steps=[]
    if h.get("status")=="RED":steps+=["Do not publish or execute a new state.","Inspect health.problems and source freshness.","Rerun only after root cause is understood."]
    if a.get("status")=="BLOCK":steps+=["Verify latest QQQ completed-session source values against an independent observation.","Do not overwrite the immutable prior decision.","Resume only after anomaly is explained or source data normalizes."]
    if not steps:steps=["No recovery action required."]
    r={"status":"RECOVERY_REQUIRED" if len(steps)>1 else "CLEAR","automatic_model_changes_allowed":False,"steps":steps}
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build_recovery_plan(),indent=2))

from __future__ import annotations
import json
from pathlib import Path
from json_artifacts import write_json_atomic
DEPS={"shadow_history/readiness.json":["shadow_history/health.json","shadow_history/anomalies.json","output/latest_signal.json"],"docs/data.json":["shadow_history/readiness.json","shadow_history/performance.json"],"shadow_history/execution_readiness.json":["shadow_history/readiness.json","shadow_history/execution_plan.json","shadow_history/execution_audit.json"]}
def build(out="shadow_history/dependency_integrity.json"):
    violations=[]
    for child,parents in DEPS.items():
        c=Path(child)
        if not c.exists():violations.append({"artifact":child,"reason":"MISSING_CHILD"});continue
        for parent in parents:
            p=Path(parent)
            if not p.exists():violations.append({"artifact":child,"dependency":parent,"reason":"MISSING_DEPENDENCY"})
            elif p.stat().st_mtime_ns>c.stat().st_mtime_ns:violations.append({"artifact":child,"dependency":parent,"reason":"DEPENDENCY_NEWER_THAN_DERIVED_ARTIFACT"})
    r={"status":"PASS" if not violations else "FAIL","checked_dependencies":sum(map(len,DEPS.values())),"violations":violations}
    write_json_atomic(out,r)
    if violations:raise RuntimeError("ARTIFACT_DEPENDENCY_INTEGRITY_FAIL:"+json.dumps(violations[:5]))
    return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

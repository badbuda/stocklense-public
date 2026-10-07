from __future__ import annotations
import json
from pathlib import Path
from json_artifacts import write_json_atomic
def build(out="shadow_history/qc_parity_dossier.json"):
    def j(p):q=Path(p);return json.loads(q.read_text()) if q.exists() else {}
    manifest=j("governance/qc_724_daily_state_manifest.json");ing=j("shadow_history/qc_input_ingestion.json");same=j("shadow_history/qc_same_input_parity.json")
    exact=bool(same.get("same_input_parity_proven"))
    r={"status":"FULL_SAME_INPUT_PARITY_PROVEN" if exact else "REFERENCE_PARITY_ONLY","reference_evidence":{"lean_sessions":manifest.get("sessions"),"daily_state_fingerprint":manifest.get("full_state_sha256"),"transition_and_execution_reference_locked":True},"same_input_evidence":{"input_export_status":ing.get("status","MISSING"),"compared_sessions":same.get("compared_sessions",0),"proven":exact},"blockers":[] if exact else ["Missing validated LEAN daily feature export with close,SMA50,SMA200,VOL20,MOM12,level,defense,leverage for all 3,774 sessions."],"claim_allowed":"Full identical-input parity." if exact else "QC reference integrity/execution parity only; do not claim full feature/input parity."}
    write_json_atomic(out,r);return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

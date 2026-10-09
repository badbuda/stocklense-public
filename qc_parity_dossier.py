"""Conservative QC/LEAN evidence ladder — no automatic parity promotion."""
from __future__ import annotations
import json
from pathlib import Path
from json_artifacts import write_json_atomic


def build(out="shadow_history/qc_parity_dossier.json"):
    def load(path):
        p=Path(path)
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    manifest=load("governance/qc_724_daily_state_manifest.json")
    ingest=load("shadow_history/qc_input_ingestion.json")
    same=load("shadow_history/qc_same_input_parity.json")
    expected=manifest.get("sessions")
    valid_input=(ingest.get("status")=="VALID" and ingest.get("rows")==expected)
    fully_compared=(same.get("compared_sessions")==expected and
                    same.get("input_validation",{}).get("status")=="VALID")
    same_input_matched=(valid_input and fully_compared and
                        same.get("same_input_state_match") is True and
                        same.get("mismatch_count")==0)
    provenance=(same_input_matched and ingest.get("source_authenticity_proven") is True
                and same.get("source_authenticity_proven") is True)
    proven=provenance and same.get("same_input_parity_proven") is True
    blockers=[]
    if not valid_input: blockers.append("Missing strict validated 3,774-session LEAN feature export.")
    if not same_input_matched: blockers.append("Python frozen state machine has not exactly matched 3,774 identical LEAN input sessions.")
    if not provenance: blockers.append("Independent authenticity of the LEAN daily feature source is not established.")
    result={
        "status":"FULL_SAME_INPUT_PARITY_PROVEN" if proven else "REFERENCE_PARITY_ONLY",
        "reference_evidence":{
            "lean_sessions":expected,
            "daily_state_fingerprint":manifest.get("full_state_sha256"),
            "transition_and_execution_reference_locked":True,
        },
        "same_input_evidence":{
            "input_export_status":ingest.get("status","MISSING"),
            "compared_sessions":same.get("compared_sessions",0),
            "structural_validation_passed":valid_input,
            "mathematical_state_match":same_input_matched,
            "native_source_provenance":provenance,
            "proven":proven,
        },
        "blockers":blockers,
        "claim_allowed":"Full identical-input parity." if proven
                        else "Immutable reference evidence only; never infer LEAN input, fill or return parity.",
        "automatic_model_change":False,
    }
    write_json_atomic(out,result)
    return result


if __name__=="__main__":
    print(json.dumps(build(),indent=2))

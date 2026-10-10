from __future__ import annotations
import json
from pathlib import Path
OUT=Path("research/lean_parity_evidence_ladder.json")
def load(p):
 q=Path(p);return json.loads(q.read_text()) if q.exists() else {}
def build(out=OUT):
 s=load("shadow_history/qc_same_input_parity.json");p=load("shadow_history/qc_portfolio_path_parity.json");b=load("research/lean_same_start_parity_blocker.json");d=load("shadow_history/qc_parity_dossier.json")
 layers=[{"layer":"reference_integrity","proven":d.get("status") in ("REFERENCE_PARITY_ONLY","FULL_SAME_INPUT_PARITY_PROVEN")},{"layer":"identical_input_state_machine","proven":bool(s.get("same_input_parity_proven"))},{"layer":"common_start_portfolio_path","proven":bool(p.get("portfolio_path_parity_proven"))},{"layer":"common_start_endpoint_and_cagr","proven":bool(p.get("return_parity_proven"))}]
 r={"schema_version":1,"status":"FULL_PARITY_PROVEN" if all(x["proven"] for x in layers) else "EVIDENCE_INCOMPLETE","layers":layers,"master_status":b.get("status"),"frozen_model_mutated":False,"claim_boundary":"Each layer requires independent evidence; later layers are not inferred from earlier layers."}
 Path(out).write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

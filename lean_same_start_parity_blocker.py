from __future__ import annotations
import json
from pathlib import Path
OUT=Path("research/lean_same_start_parity_blocker.json")
def build(same="shadow_history/qc_same_input_parity.json",dossier="shadow_history/qc_parity_dossier.json",portfolio="shadow_history/qc_portfolio_path_parity.json",out=OUT):
 def load(p):
  q=Path(p);return json.loads(q.read_text()) if q.exists() else {}
 s=load(same);d=load(dossier);p=load(portfolio);compared=int(s.get("compared_sessions",0))
 state_proven=bool(s.get("same_input_parity_proven")) and compared>0
 endpoint_proven=bool(p.get("portfolio_path_parity_proven")) and bool(p.get("return_parity_proven")) and int(p.get("compared_sessions",0))>0
 blockers=([] if state_proven else ["Missing validated LEAN daily feature export required for identical-input state comparison."])+([] if endpoint_proven else ["Missing common-start LEAN portfolio/NAV path export/reference comparison required for endpoint/return parity."])
 result={"schema_version":3,"status":"FULL_PARITY_PROVEN" if state_proven and endpoint_proven else ("STATE_PARITY_PROVEN_ENDPOINT_BLOCKED" if state_proven else "BLOCKED"),"kind":"LEAN_IDENTICAL_INPUT_STATE_AND_COMMON_START_ENDPOINT_PARITY","same_input_state_parity_proven":state_proven,"common_start_endpoint_parity_proven":endpoint_proven,"common_start_return_parity_proven":endpoint_proven,"portfolio_parity_status":p.get("status","MISSING"),"compared_sessions":compared,"reference_parity_status":d.get("status","MISSING"),"scientific_blockers":blockers,"claims_allowed":(["Full identical-input state-machine parity"] if state_proven else ["QC reference integrity/execution parity only"])+(["Common-start portfolio/NAV path and derived return parity"] if endpoint_proven else []),"claims_forbidden":[] if state_proven and endpoint_proven else (["Common-start portfolio/NAV parity","LEAN-confirmed historical CAGR parity"] if not endpoint_proven else []),"promotion_allowed":False,"frozen_model_mutated":False,"interpretation":"State equality and portfolio-path/return equality are independent evidence layers. Historical CAGR parity is allowed only after both pass."}
 Path(out).write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build(),indent=2))

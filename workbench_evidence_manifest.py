from __future__ import annotations
import hashlib,json
from pathlib import Path
FILES=["historical_replay/daily_states.csv","governance/qc_724_leverage_transitions.json","governance/qc_724_order_golden_master.json","governance/qc_724_daily_state_manifest.json","dashboard_workbench.py","docs/workbench.html"]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def build(out="docs/workbench_evidence_manifest.json"):
 d={"schema_version":1,"kind":"WORKBENCH_EVIDENCE_MANIFEST","model":"StockLens 8.0 FROZEN","automatic_model_change":False,"automatic_promotion":False,"artifacts":{p:sha(p) for p in FILES},"evidence_classes":{"historical_replay":"REPLAY_APPROXIMATION","lean_transitions":"VERIFIED_GOLDEN_MASTER","lean_daily_state":"VERIFIED_FINGERPRINT_RAW_ROWS_MISSING","prospective":"IMMATURE_FUTURE_ONLY"}}
 canonical=json.dumps(d,sort_keys=True,separators=(",",":"));d["manifest_sha256"]=hashlib.sha256(canonical.encode()).hexdigest();Path(out).write_text(json.dumps(d,indent=2)+"\n");return d
if __name__=="__main__":print(json.dumps(build(),indent=2))

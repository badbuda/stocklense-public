from __future__ import annotations
import json
from pathlib import Path
EXPORTER=Path("integrations/lean_feature_evidence_exporter.py")
SCHEMA=Path("governance/qc_lean_feature_export_schema.json")
OUT=Path("research/lean_feature_export_readiness.json")
def build(out=OUT):
 s=json.loads(SCHEMA.read_text());src=EXPORTER.read_text()
 required=s["required_columns"]
 checks={"exporter_exists":EXPORTER.exists(),"schema_columns_embedded":all(('"%s"'%c) in src for c in required),
  "observational_only":all(x not in src for x in ("next_level(","defense_active(","SetHoldings(","MarketOrder(")),
  "object_store_delivery":"ObjectStore.Save" in src,
  "downstream_validator_present":Path("qc_input_ingestion.py").exists(),
  "downstream_comparator_present":Path("qc_same_input_parity.py").exists()}
 ready=all(checks.values())
 r={"schema_version":1,"status":"READY_FOR_LEAN_EXPORT" if ready else "INCOMPLETE","checks":checks,
  "expected_sessions":s["expected_sessions"],"boundaries":[s["first_date"],s["last_date"]],
  "artifact_key":"stocklens/qc_lean_daily_features.csv",
  "next_step":"Run/instrument the frozen LEAN algorithm, retrieve the Object Store CSV without modification, place it at governance/qc_lean_daily_features.csv, then let qc_input_ingestion.py and qc_same_input_parity.py validate it.",
  "current_parity_proven":False,"automatic_promotion":False,"frozen_model_mutated":False}
 Path(out).write_text(json.dumps(r,indent=2)+"\n")
 if not ready:raise RuntimeError("LEAN_EXPORT_PATH_INCOMPLETE")
 return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

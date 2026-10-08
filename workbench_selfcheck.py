from __future__ import annotations
import json
from pathlib import Path
def check(validate_existing_bundle=True):
 w=json.loads(Path("docs/workbench.json").read_text());m=json.loads(Path("docs/workbench_evidence_manifest.json").read_text())
 errors=[]
 if w["model"]!="StockLens 8.0 FROZEN":errors.append("MODEL")
 if w["replay"]["sessions"]!=len(w["replay"]["rows"]):errors.append("REPLAY_COUNT")
 if w["regime_analytics"]["transition_count"]!=67:errors.append("TRANSITION_COUNT")
 if w["regime_analytics"]["source_transition_sha256"]!="5561588a3bcd8a416cc13320536d7d3ff51bdb6de418e4f2c31b85eaf2ac745b":errors.append("TRANSITION_SHA")
 if m["automatic_model_change"] or m["automatic_promotion"]:errors.append("GOVERNANCE")
 if m["evidence_classes"]["historical_replay"]!="REPLAY_APPROXIMATION":errors.append("EVIDENCE_CLASS")
 bundle=Path("docs/workbench_evidence_bundle.json")
 if validate_existing_bundle and bundle.exists():
  b=json.loads(bundle.read_text())
  if b.get("model")!=w["model"]:errors.append("BUNDLE_MODEL")
  if b.get("evidence_manifest",{}).get("manifest_sha256")!=m.get("manifest_sha256"):errors.append("BUNDLE_MANIFEST")
  if b.get("replay",{}).get("dataset_sha256")!=w["replay"].get("dataset_sha256"):errors.append("BUNDLE_REPLAY_SHA")
 return {"status":"PASS" if not errors else "FAIL","errors":errors,"replay_sessions":w["replay"]["sessions"],"transition_count":w["regime_analytics"]["transition_count"],"manifest_sha256":m["manifest_sha256"],"automatic_model_change":False}
def build(out="docs/workbench_selfcheck.json"):
 d=check();Path(out).write_text(json.dumps(d,indent=2)+"\n")
 if d["status"]!="PASS":raise SystemExit("Workbench self-check failed: "+",".join(d["errors"]))
 return d
if __name__=="__main__":print(json.dumps(build(),indent=2))

from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
def load(p): return json.loads(Path(p).read_text())
def build(out="docs/workbench_evidence_bundle.json"):
 w=load("docs/workbench.json");m=load("docs/workbench_evidence_manifest.json");s=load("docs/workbench_selfcheck.json")
 if s.get("status")!="PASS": raise RuntimeError("WORKBENCH_SELFCHECK_NOT_PASS")
 if s.get("manifest_sha256")!=m.get("manifest_sha256"): raise RuntimeError("MANIFEST_SELFCHECK_MISMATCH")
 d={"schema_version":1,"kind":"STOCKLENS_WORKBENCH_CANONICAL_EVIDENCE_BUNDLE","generated_at_utc":datetime.now(timezone.utc).isoformat(),"model":w["model"],"self_check":s,"evidence_manifest":m,"live":{"asof_date":w["live"].get("asof_date"),"action":w["live"].get("action"),"level":w["live"].get("level"),"target_leverage":w["live"].get("target_leverage")},"replay":{"start":w["replay"]["start"],"end":w["replay"]["end"],"sessions":w["replay"]["sessions"],"dataset_sha256":w["replay"]["dataset_sha256"]},"regime_analytics":w["regime_analytics"],"constraints":w["constraints"],"automatic_model_change":False,"automatic_promotion":False}
 Path(out).write_text(json.dumps(d,indent=2)+"\n")
 return d
if __name__=="__main__": print(json.dumps(build(),indent=2))

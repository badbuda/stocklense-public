from __future__ import annotations
import hashlib,json,os,subprocess
from pathlib import Path

def canonical_sha(value):
 return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def _git_sha():
 sha=os.getenv("GITHUB_SHA")
 if sha:return sha
 try:return subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
 except Exception:return None

def identity(workbench_path="docs/workbench.json",evidence_path=None):
 """Canonical publication generation identity.

 Deliberately depends only on already-built Workbench source state plus the
 publisher git SHA. Downstream evidence-health artifacts are excluded so every
 artifact in one publication can compute the same identity before/after health
 materialization without circular or previous-generation coupling.
 """
 w=json.loads(Path(workbench_path).read_text())
 replay=w.get("replay",{})
 rows=replay.get("rows") or []
 contract=w.get("simulator_contract")
 if not rows or not contract: raise RuntimeError("PUBLICATION_IDENTITY_SOURCE_MISSING")
 source={
  "schema_version":2,
  "git_sha":_git_sha(),
  "signal_asof":replay.get("signal_asof") or w.get("signal_asof"),
  "replay_dataset_sha256":replay.get("dataset_sha256"),
  "replay_rows_sha256":canonical_sha(rows),
  "simulator_contract_sha256":canonical_sha(contract),
 }
 if not source["git_sha"]:
  raise RuntimeError("PUBLICATION_IDENTITY_GIT_SHA_MISSING")
 if not source["replay_dataset_sha256"]:
  raise RuntimeError("PUBLICATION_IDENTITY_DATASET_FINGERPRINT_MISSING")
 source["generation_id"]=canonical_sha(source)
 return source

from __future__ import annotations
import json,os,subprocess
from pathlib import Path
from json_artifacts import write_json_atomic
def _git_sha():
    sha=os.getenv("GITHUB_SHA")
    if sha:return sha
    try:return subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    except Exception:return None
def build(out="shadow_history/publication_gate.json"):
    def j(p):q=Path(p);return json.loads(q.read_text()) if q.exists() else {}
    provenance=j("output/research_provenance.json");manifest=j("shadow_history/run_manifest.json");git_sha=_git_sha()
    try:
        from publication_identity import identity
        canonical_generation=identity().get("generation_id")
    except Exception:
        canonical_generation=None
    checks={
        "pipeline_validation":j("shadow_history/pipeline_validation.json").get("status")=="PASS",
        "dependency_integrity":j("shadow_history/dependency_integrity.json").get("status")=="PASS",
        "artifact_integrity":j("shadow_history/artifact_integrity.json").get("status")=="PASS",
        "artifact_catalog_present":Path("shadow_history/artifact_catalog.json").exists(),
        "incident_clear":j("shadow_history/incident_state.json").get("status")=="CLEAR",
        "git_identity_present":bool(git_sha),
        "provenance_current_commit":bool(git_sha) and provenance.get("git_sha")==git_sha,
        "manifest_current_commit":bool(git_sha) and manifest.get("git_sha")==git_sha,
        "canonical_generation_present":bool(canonical_generation),
        "provenance_generation_canonical":bool(canonical_generation) and provenance.get("publication_generation")==canonical_generation,
        "manifest_generation_canonical":bool(canonical_generation) and manifest.get("publication_generation")==canonical_generation,
    }
    r={"status":"ALLOW" if all(checks.values()) else "BLOCK","checks":checks,"source_git_sha":git_sha,"publication_generation":canonical_generation,"rule":"Evidence publication is allowed only from a complete internally consistent run. Remote branch freshness is enforced by workflow before push."}
    write_json_atomic(out,r)
    if r["status"]!="ALLOW":raise RuntimeError("PUBLICATION_GATE_BLOCKED:"+json.dumps(checks))
    return r
if __name__=="__main__":print(json.dumps(build(),indent=2))

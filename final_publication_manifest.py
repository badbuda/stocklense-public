from __future__ import annotations
import hashlib,json,os,subprocess
from datetime import datetime,timezone
from pathlib import Path
from json_artifacts import write_json_atomic

TRACK=[
"output/research_provenance.json",
"shadow_history/run_manifest.json",
"shadow_history/artifact_integrity.json",
"shadow_history/pipeline_validation.json",
"shadow_history/publication_gate.json",
"docs/data.json",
]

def _git_sha():
    sha=os.getenv("GITHUB_SHA")
    if sha:return sha
    try:return subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    except Exception:return None

def build(out="shadow_history/final_publication_manifest.json"):
    provenance=json.loads(Path("output/research_provenance.json").read_text())
    pre_manifest=json.loads(Path("shadow_history/run_manifest.json").read_text())
    gate=json.loads(Path("shadow_history/publication_gate.json").read_text())
    integrity=json.loads(Path("shadow_history/artifact_integrity.json").read_text())
    pipeline=json.loads(Path("shadow_history/pipeline_validation.json").read_text())
    control=json.loads(Path("docs/data.json").read_text())
    git_sha=_git_sha()
    generation=provenance.get("publication_generation")
    try:
        from publication_identity import identity
        canonical_generation=identity().get("generation_id")
    except Exception:
        canonical_generation=None
    if not git_sha or provenance.get("git_sha")!=git_sha or gate.get("source_git_sha")!=git_sha:
        raise RuntimeError("FINAL_PUBLICATION_GIT_IDENTITY_MISMATCH")
    if not generation or not canonical_generation:
        raise RuntimeError("FINAL_PUBLICATION_GENERATION_MISSING")
    if generation!=canonical_generation or gate.get("publication_generation")!=canonical_generation:
        raise RuntimeError("FINAL_PUBLICATION_CANONICAL_GENERATION_MISMATCH")
    if pre_manifest.get("git_sha")!=git_sha or pre_manifest.get("publication_generation")!=generation:
        raise RuntimeError("FINAL_PUBLICATION_PRE_MANIFEST_IDENTITY_MISMATCH")
    if integrity.get("status")!="PASS" or pipeline.get("status")!="PASS" or gate.get("status")!="ALLOW":
        raise RuntimeError("FINAL_PUBLICATION_NOT_ALLOWED")
    control_gate=control.get("publication_gate",{})
    if control_gate.get("status")!="ALLOW" or control_gate.get("authoritative") is not True:
        raise RuntimeError("FINAL_PUBLICATION_CONTROL_CENTER_NOT_AUTHORITATIVE")
    files=[]
    for name in TRACK:
        p=Path(name)
        if not p.exists():raise RuntimeError("FINAL_PUBLICATION_ARTIFACT_MISSING:"+name)
        files.append({"path":name,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size})
    result={
        "schema_version":1,"kind":"FINAL_PUBLICATION_MANIFEST",
        "generated_at_utc":datetime.now(timezone.utc).isoformat(),
        "git_sha":git_sha,"publication_generation":generation,
        "github_run_id":os.getenv("GITHUB_RUN_ID"),"github_run_number":os.getenv("GITHUB_RUN_NUMBER"),
        "status":"PASS","files":files,
    }
    write_json_atomic(out,result);return result

def validate(path="shadow_history/final_publication_manifest.json"):
    p=Path(path)
    try:manifest=json.loads(p.read_text())
    except Exception as exc:raise RuntimeError("FINAL_PUBLICATION_MANIFEST_MISSING_OR_INVALID") from exc
    if manifest.get("kind")!="FINAL_PUBLICATION_MANIFEST" or manifest.get("status")!="PASS":
        raise RuntimeError("FINAL_PUBLICATION_MANIFEST_STATUS_INVALID")
    git_sha=_git_sha()
    if not git_sha or manifest.get("git_sha")!=git_sha:
        raise RuntimeError("FINAL_PUBLICATION_MANIFEST_GIT_MISMATCH")
    try:
        from publication_identity import identity
        canonical_generation=identity().get("generation_id")
    except Exception:
        canonical_generation=None
    if not canonical_generation or manifest.get("publication_generation")!=canonical_generation:
        raise RuntimeError("FINAL_PUBLICATION_MANIFEST_GENERATION_MISMATCH")
    listed=manifest.get("files") or []
    if {x.get("path") for x in listed}!=set(TRACK):
        raise RuntimeError("FINAL_PUBLICATION_MANIFEST_TRACK_SET_MISMATCH")
    for item in listed:
        source=Path(item["path"])
        if not source.exists():raise RuntimeError("FINAL_PUBLICATION_MANIFEST_SOURCE_MISSING:"+item["path"])
        actual_sha=hashlib.sha256(source.read_bytes()).hexdigest()
        if actual_sha!=item.get("sha256") or source.stat().st_size!=item.get("bytes"):
            raise RuntimeError("FINAL_PUBLICATION_MANIFEST_DIGEST_MISMATCH:"+item["path"])
    return manifest

if __name__=="__main__":
    built=build()
    validate()
    print(json.dumps(built,indent=2))

from __future__ import annotations
import hashlib,json,os,subprocess
from pathlib import Path
from json_artifacts import write_json_atomic

def _git_sha():
    sha=os.getenv("GITHUB_SHA")
    if sha:return sha
    try:return subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    except Exception:return None

def _generation_identity():
    try:
        from publication_identity import identity
        d=identity()
        return d.get("generation_id") or d.get("generation_identity") or d.get("publication_generation")
    except Exception:
        return None

def build(dataset="docs/research.json",out="output/research_provenance.json"):
    p=Path(dataset)
    raw=p.read_bytes()
    x=json.loads(raw)
    rows=x.get("rows",[])
    r={
        "schema_version":2,
        "kind":"RESEARCH_PROVENANCE",
        "dataset_path":str(p),
        "dataset_sha256":hashlib.sha256(raw).hexdigest(),
        "rows":len(rows),
        "first_date":rows[0]["date"] if rows else None,
        "last_date":rows[-1]["date"] if rows else None,
        "baseline":x.get("baseline"),
        "mode":x.get("mode"),
        "factor_coverage":x.get("factor_coverage",{}),
        "git_sha":_git_sha(),
        "github_run_id":os.getenv("GITHUB_RUN_ID"),
        "github_run_number":os.getenv("GITHUB_RUN_NUMBER"),
        "publication_generation":_generation_identity(),
        "promotion_allowed":False,
        "automatic_model_change":False,
    }
    if not r["git_sha"]:
        raise RuntimeError("RESEARCH_PROVENANCE_GIT_SHA_MISSING")
    if not r["publication_generation"]:
        raise RuntimeError("RESEARCH_PROVENANCE_GENERATION_MISSING")
    write_json_atomic(out,r)
    return r

if __name__=="__main__":print(json.dumps(build(),indent=2))

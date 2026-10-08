from __future__ import annotations
import hashlib,json,os,subprocess
from datetime import datetime,timezone
from pathlib import Path
def _git_sha():
    sha=os.getenv("GITHUB_SHA")
    if sha:return sha
    try:return subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
    except Exception:return None

TRACK=[
"output/latest_signal.json","output/research_provenance.json","shadow_history/health.json","shadow_history/readiness.json","shadow_history/performance.json",
"shadow_history/benchmark.json","shadow_history/anomalies.json","shadow_history/data_provenance.json",
"shadow_history/qc_parity_dossier.json","shadow_history/forward_path.json","shadow_history/forward_quality.json",
"shadow_history/execution_quality.json","shadow_history/execution_audit.json","shadow_history/execution_readiness.json",
"research/prospective/registry.json","docs/prospective_maturity.json","docs/capital_readiness.json",
"shadow_history/incident_state.json","shadow_history/dependency_integrity.json","shadow_history/artifact_catalog.json"]
def build_run_manifest(out="shadow_history/run_manifest.json"):
    files=[]
    for n in TRACK:
        p=Path(n)
        if p.exists(): files.append({"path":n,"sha256":hashlib.sha256(p.read_bytes()).hexdigest(),"bytes":p.stat().st_size})
    provenance={}
    pp=Path("output/research_provenance.json")
    if pp.exists():
        provenance=json.loads(pp.read_text())
    r={"schema_version":2,"generated_at_utc":datetime.now(timezone.utc).isoformat(),"github_run_id":os.getenv("GITHUB_RUN_ID"),"github_run_number":os.getenv("GITHUB_RUN_NUMBER"),"git_sha":_git_sha(),"publication_generation":provenance.get("publication_generation"),"files":files}
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build_run_manifest(),indent=2))

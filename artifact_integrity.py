from __future__ import annotations
import hashlib,json
from pathlib import Path
from json_artifacts import validate_json_files,write_json_atomic

CRITICAL=[
    "output/latest_signal.json","output/research_provenance.json","shadow_history/health.json",
    "shadow_history/readiness.json","shadow_history/anomalies.json","shadow_history/recovery_plan.json",
    "shadow_history/data_provenance.json","shadow_history/daily_digest.json","shadow_history/slo.json",
    "shadow_history/experiment_quality.json","shadow_history/artifact_catalog.json",
    "shadow_history/run_manifest.json","research/prospective/registry.json","docs/prospective_maturity.json","docs/capital_readiness.json","docs/data.json",
]

def _semantic_failures():
    bad=[]
    try:
        p=json.load(open("output/research_provenance.json"))
        required=("dataset_sha256","git_sha","publication_generation","promotion_allowed","automatic_model_change")
        missing=[k for k in required if k not in p or p[k] is None]
        if missing:bad.append({"path":"output/research_provenance.json","error":"missing:"+",".join(missing)})
        if p.get("promotion_allowed") is not False:bad.append({"path":"output/research_provenance.json","error":"promotion_allowed_must_be_false"})
        if p.get("automatic_model_change") is not False:bad.append({"path":"output/research_provenance.json","error":"automatic_model_change_must_be_false"})
    except Exception as e:bad.append({"path":"output/research_provenance.json","error":str(e)})
    try:
        registry=json.load(open("research/prospective/registry.json"))
        provenance=json.load(open("output/research_provenance.json"))
        if registry.get("producer_git_sha")!=provenance.get("git_sha"):bad.append({"path":"research/prospective/registry.json","error":"producer_git_sha_mismatch_with_research_provenance"})
        if registry.get("ingestion_gate")!="STRICTLY_AFTER_INCEPTION_AND_COMPLETED_XNYS":bad.append({"path":"research/prospective/registry.json","error":"prospective_ingestion_gate_invalid"})
        if not registry.get("updated_at_utc"):bad.append({"path":"research/prospective/registry.json","error":"prospective_registry_timestamp_missing"})
        candidates=registry.get("candidates",[]);audits=registry.get("last_ingestion_audit",[])
        if registry.get("candidate_count")!=len(candidates) or registry.get("audit_count")!=len(audits) or {x.get("experiment_id") for x in candidates}!={x.get("experiment_id") for x in audits}:bad.append({"path":"research/prospective/registry.json","error":"prospective_audit_coverage_invalid"})
        if candidates and any(not x.get("definition_fingerprint") for x in candidates):bad.append({"path":"research/prospective/registry.json","error":"prospective_definition_fingerprint_missing"})
        if audits and any(x.get("definition_matches_registration") is not True for x in audits):bad.append({"path":"research/prospective/registry.json","error":"prospective_definition_drift"})
    except Exception as e:bad.append({"path":"research/prospective/registry.json","error":str(e)})
    try:
        manifest=json.load(open("shadow_history/run_manifest.json"))
        entries={x.get("path"):x for x in manifest.get("files",[])}
        provenance=json.load(open("output/research_provenance.json"))
        if manifest.get("git_sha")!=provenance.get("git_sha"):bad.append({"path":"shadow_history/run_manifest.json","error":"git_sha_mismatch_with_research_provenance"})
        if manifest.get("publication_generation")!=provenance.get("publication_generation"):bad.append({"path":"shadow_history/run_manifest.json","error":"publication_generation_mismatch_with_research_provenance"})
        for governed in ("research/prospective/registry.json","docs/prospective_maturity.json","docs/capital_readiness.json"):
            entry=entries.get(governed)
            if not entry:bad.append({"path":"shadow_history/run_manifest.json","error":"governance_artifact_not_tracked:"+governed})
            elif not Path(governed).exists():bad.append({"path":governed,"error":"governance_artifact_missing"})
            elif entry.get("sha256")!=hashlib.sha256(Path(governed).read_bytes()).hexdigest():bad.append({"path":governed,"error":"run_manifest_sha256_mismatch"})
        path="output/research_provenance.json";entry=entries.get(path)
        if not entry:bad.append({"path":"shadow_history/run_manifest.json","error":"research_provenance_not_tracked"})
        elif Path(path).exists() and entry.get("sha256")!=hashlib.sha256(Path(path).read_bytes()).hexdigest():bad.append({"path":path,"error":"run_manifest_sha256_mismatch"})
    except Exception as e:bad.append({"path":"shadow_history/run_manifest.json","error":str(e)})
    return bad

def validate_artifacts(out="shadow_history/artifact_integrity.json"):
    bad=validate_json_files(CRITICAL);bad.extend(_semantic_failures())
    result={"schema_version":1,"kind":"ARTIFACT_INTEGRITY","status":"PASS" if not bad else "FAIL","checked":len(CRITICAL),"invalid":bad}
    write_json_atomic(out,result)
    if bad:raise RuntimeError("JSON_ARTIFACT_INTEGRITY_FAIL:"+json.dumps(bad))
    return result

if __name__=="__main__":print(json.dumps(validate_artifacts(),indent=2))

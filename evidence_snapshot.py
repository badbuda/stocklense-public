from __future__ import annotations
import hashlib,json
from pathlib import Path
FILES=[
"governance/qc_724_daily_state_manifest.json","governance/qc_724_order_golden_master.json","governance/qc_lean_feature_export_schema.json",
"shadow_history/health.json","shadow_history/readiness.json","shadow_history/qc_daily_parity.json","shadow_history/qc_parity_dossier.json",
"shadow_history/data_provenance.json","shadow_history/anomalies.json","shadow_history/execution_audit.json","shadow_history/forward_quality.json","shadow_history/market_context.json","shadow_history/context_quality.json","shadow_history/context_analytics.json"]
def build_evidence_snapshot(out_path="shadow_history/evidence_snapshot.json"):
    items=[]
    for name in FILES:
        p=Path(name)
        if p.exists():
            b=p.read_bytes();items.append({"path":name,"sha256":hashlib.sha256(b).hexdigest(),"bytes":len(b)})
    result={"schema_version":1,"files":items,"count":len(items)}
    p=Path(out_path);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__": print(json.dumps(build_evidence_snapshot(),indent=2))

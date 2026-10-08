from __future__ import annotations
import json
from pathlib import Path
def build_experiment_quality(out="shadow_history/experiment_quality.json"):
    def j(p,d=None):
        q=Path(p);return json.loads(q.read_text()) if q.exists() else (d or {})
    m=j("shadow_history/evidence_maturity.json");h=j("shadow_history/health.json");q=j("shadow_history/qc_daily_parity.json")
    gates={"pipeline_green":h.get("status")=="GREEN","prospective_sample_interpretable":m.get("performance_interpretation_allowed",False),
           "qc_reference_integrity":q.get("reference_integrity",{}).get("status")=="PASS"}
    r={"status":"INTERPRETABLE" if all(gates.values()) else "LIMITED","gates":gates,
       "historical_qc_record_is_reference_not_live_proof":True,"prospective_and_historical_evidence_kept_separate":True}
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build_experiment_quality(),indent=2))

from __future__ import annotations
import csv,json
from pathlib import Path
from prospective_gate import gated_ledger_rows,GATE
def build_evidence_maturity(out="shadow_history/evidence_maturity.json"):
    def rows(p):
        q=Path(p);return list(csv.DictReader(q.open())) if q.exists() else []
    paper,rejected,inception=gated_ledger_rows();signals=rows("shadow_history/signals.csv")
    n=len(paper);transitions=sum(r.get("action") not in ("","NO_CHANGE") for r in signals)
    if n<20: stage="BOOTSTRAP"
    elif n<63: stage="EARLY"
    elif n<252: stage="FORMING"
    else: stage="MATURE"
    r={"stage":stage,"prospective_sessions":n,"prospective_signal_sessions":len(signals),"prospective_transitions":transitions,
       "performance_interpretation_allowed":n>=63,"strong_live_claims_allowed":n>=252,
       "warning":"Do not infer live performance quality from a short prospective sample." if n<63 else None,"experiment_id":"SL9-007-UPSHIFT-CONFIRMATION","inception_date":inception.isoformat(),"rejected_pre_inception_or_invalid":len(rejected),"gate":GATE}
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2)+"\n");return r
if __name__=="__main__":print(json.dumps(build_evidence_maturity(),indent=2))

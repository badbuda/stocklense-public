from __future__ import annotations
import json
from pathlib import Path

def _j(p,d=None):
    q=Path(p); return json.loads(q.read_text()) if q.exists() else (d or {})

def _research_snapshot():
    q=_j("research/queue.json",{"experiments":[]})
    a=_j("research/AUTONOMY_STATE.json",{})
    governance={}
    for x in a.get("failed_hypotheses",[]): governance[x.get("id")]={"status":x.get("status"),"reason":x.get("reason")}
    for x in a.get("blocked_experiments",[]): governance[x.get("id")]={"status":"BLOCKED","reason":x.get("reason")}
    for x in a.get("active_experiments",[]): governance[x.get("id")]={"status":x.get("status"),"reason":"Active prospective evidence collection; no automatic promotion."}
    rows=[]
    for e in q.get("experiments",[]):
        rp=e.get("result_path");payload=_j(rp).get("payload",{}) if rp and Path(rp).exists() else {}
        periods=payload.get("periods",{});holdout=periods.get("holdout",{});g=governance.get(e.get("experiment_id"),{})
        rows.append({
            "experiment_id":e.get("experiment_id"),"name":e.get("name"),
            "result_status":payload.get("status") or e.get("status"),
            "governance_status":g.get("status") or ("COMPLETED_UNGOVERNED" if payload else e.get("status")),
            "governance_reason":g.get("reason"),
            "development_excess_cagr":periods.get("development",{}).get("excess_cagr"),
            "validation_excess_cagr":periods.get("validation",{}).get("excess_cagr"),
            "holdout_excess_cagr":holdout.get("excess_cagr"),
            "holdout_max_drawdown":holdout.get("max_drawdown"),
            "holdout_baseline_max_drawdown":holdout.get("benchmark_max_drawdown"),
            "holdout_drawdown_delta":holdout.get("drawdown_delta"),
            "changed_sessions":payload.get("intervention",{}).get("changed_sessions"),
            "automatic_promotion":False,
        })
    return {"completed_results":sum(x.get("result_status") is not None for x in rows),"experiments":rows,"policy":"GOVERNANCE_STATUS_AUTHORITATIVE_RESULT_STATUS_DESCRIPTIVE_NO_AUTOMATIC_PROMOTION"}

def build_daily_digest(out="shadow_history/daily_digest.json"):
    s=_j("output/latest_signal.json");r=_j("shadow_history/readiness.json");h=_j("shadow_history/health.json");b=_j("shadow_history/benchmark.json")
    integrity=_j("shadow_history/artifact_integrity.json",{"status":"PENDING"})
    gate=_j("shadow_history/publication_gate.json",{"status":"UNKNOWN"})
    paper=_j("paper_portfolio/state.json")
    x=s.get("latest",{})
    summary=f"{x.get('asof_date','?')} | L{x.get('level','?')} {x.get('target_leverage','?')}x | {s.get('action','?')} | Health {h.get('status','?')} | {r.get('status','?')}"
    result={"schema_version":2,"summary":summary,"signal_date":x.get("asof_date"),"level":x.get("level"),"leverage":x.get("target_leverage"),"action":s.get("action"),"health":h.get("status"),"readiness":r.get("status"),"execution_required":r.get("execution_required",False),"benchmark_status":b.get("status"),"paper":{"last_executed_signal_date":paper.get("last_executed_signal_date"),"last_mark_date":paper.get("last_mark_date"),"cash":paper.get("cash"),"shares":paper.get("shares"),"status":"ACTIVE" if paper.get("last_mark_date") else "WAITING_FOR_FIRST_VALID_PROSPECTIVE_EXECUTION"},"research":_research_snapshot(),"artifact_integrity_status":integrity.get("status","PENDING"),"publication_gate_status":gate.get("status","UNKNOWN"),"human_attention_required":h.get("status")=="RED" or r.get("status")=="BLOCKED" or r.get("execution_required",False) or integrity.get("status")!="PASS" or gate.get("status")!="ALLOW"}
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,indent=2)+"\n");return result
if __name__=="__main__":print(json.dumps(build_daily_digest(),indent=2))

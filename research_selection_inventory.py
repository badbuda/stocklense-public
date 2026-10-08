"""Model-selection leakage inventory; never bless reused historical holdouts."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path

RESULTS = "docs/research_results.json"
QUEUE = "research/queue.json"
OUT = "research/selection_bias_inventory.json"
PUBLIC = "docs/selection_bias_inventory.json"


def build(*, results_path=RESULTS, queue_path=QUEUE, out=OUT, public_out=PUBLIC):
    path, qp = Path(results_path), Path(queue_path)
    results = json.loads(path.read_text())
    queue = json.loads(qp.read_text())
    entries = results.get("results", [])
    experiments = queue.get("experiments", [])
    if not isinstance(entries, list) or not isinstance(experiments, list):
        raise ValueError("INVALID_RESEARCH_INVENTORY")
    status_counts = {}
    families = {}
    for item in entries:
        if not isinstance(item, dict):
            raise ValueError("INVALID_RESEARCH_RESULT_ROW")
        status = item.get("status") or "UNKNOWN"
        status_counts[status] = status_counts.get(status, 0) + 1
        eid = (item.get("technical_result") or {}).get("experiment_id") or item.get("experiment_id")
        if eid:
            families[eid] = families.get(eid, 0) + 1
    fingerprints = {
        "research_results_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "research_queue_sha256": hashlib.sha256(qp.read_bytes()).hexdigest(),
    }
    report = {
        "schema_version": 1,
        "status": "SELECTION_INDEPENDENCE_NOT_ESTABLISHED",
        "source_fingerprints": fingerprints,
        "recorded_research_results": len(entries),
        "queued_hypotheses": len(experiments),
        "result_status_counts": status_counts,
        "per_experiment_result_counts": dict(sorted(families.items())),
        "full_variant_search_count_known": False,
        "holdout_never_reused_proven": False,
        "post_selection_significance_proven": False,
        "independent_third_party_reproduction": False,
        "allowed_claim": "Inventory of available records only; not complete candidate-selection history.",
        "unresolved": [
            "Full chronology of all internal and manual parameter tests",
            "Which historical intervals were viewed during selection",
            "Multiple-testing adjustment across all candidates",
            "One truly untouched forward dataset with frozen protocol",
            "Independent replication from source snapshots and execution records",
        ],
        "automatic_model_promotion": False,
        "live_trading_authorized": False,
    }
    for dest in (out, public_out):
        p = Path(dest)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(report, indent=2) + "\n")
    return report


if __name__ == "__main__":
    report = build()
    print(json.dumps({"status": report["status"],
                      "records": report["recorded_research_results"],
                      "hypotheses": report["queued_hypotheses"]}))

from __future__ import annotations
import hashlib,json
from pathlib import Path

DEFINITION_FIELDS=("experiment_id","name","hypothesis","baseline","research_family","predeclaration","predeclared_parameters","predeclared_objective","selection_rule")

def definition_payload(experiment):
    return {k:experiment.get(k) for k in DEFINITION_FIELDS}

def definition_fingerprint(experiment):
    raw=json.dumps(definition_payload(experiment),sort_keys=True,separators=(",",":")).encode()
    return hashlib.sha256(raw).hexdigest()

def queue_experiment(experiment_id,queue_path="research/queue.json"):
    q=json.loads(Path(queue_path).read_text())
    return next((x for x in q.get("experiments",[]) if x.get("experiment_id")==experiment_id),None)

def lineage(experiment_id,registered_evidence_fingerprint=None,queue_path="research/queue.json"):
    experiment=queue_experiment(experiment_id,queue_path)
    if not experiment:raise RuntimeError("PROSPECTIVE_LINEAGE_QUEUE_EXPERIMENT_MISSING:"+experiment_id)
    return {
      "experiment_id":experiment_id,
      "definition_fingerprint":definition_fingerprint(experiment),
      "current_evidence_fingerprint":experiment.get("fingerprint"),
      "registered_evidence_fingerprint":registered_evidence_fingerprint,
      "evidence_fingerprint_changed":bool(registered_evidence_fingerprint and experiment.get("fingerprint")!=registered_evidence_fingerprint),
      "definition_payload":definition_payload(experiment),
      "semantics":"Definition fingerprint excludes mutable result/data evidence. Evidence fingerprint drift is recorded separately and never rewrites prospective registration history.",
    }

"""Two-lane StockLens gate: safe shadow publication != research/capital promotion.

An *audited evidence-fingerprint drift* is retained as ATTENTION in the research
report and disqualifies maturity/capital claims. It must not suppress a correctly
validated frozen-8.0 SHADOW_ONLY signal after a fully consistent pipeline.
Unknown/blocked/unaudited research evidence remains fail-closed.
"""
from __future__ import annotations

import re

HEX_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
DRIFT = "ATTENTION_PROSPECTIVE_EVIDENCE_FINGERPRINT_DRIFT"


def disposition(maturity: dict) -> tuple[bool, str]:
    if not isinstance(maturity, dict):
        return False, "MALFORMED_RESEARCH_MATURITY"
    if maturity.get("schema_version") != 6:
        return False, "UNEXPECTED_MATURITY_SCHEMA"
    producer = maturity.get("producer_git_sha")
    if (maturity.get("producer_current") is not True
            or not isinstance(producer, str) or not HEX_SHA256.fullmatch(producer)
            or maturity.get("current_git_sha") != producer):
        return False, "RESEARCH_PRODUCER_UNVERIFIED"
    experiments = maturity.get("experiments")
    if not isinstance(experiments, list) or not experiments:
        return False, "NO_RESEARCH_EXPERIMENT_AUDIT"
    ids = [x.get("experiment_id") for x in experiments if isinstance(x, dict)]
    if len(ids) != len(experiments) or any(not x for x in ids) or len(set(ids)) != len(ids):
        return False, "RESEARCH_AUDIT_COVERAGE_INVALID"
    if any(
        x.get("status") != "ACTIVE_RESEARCH_ONLY"
        or x.get("automatic_promotion") is not False
        or x.get("definition_current") is not True
        or x.get("audit_schema_complete") is not True
        or x.get("persistence_consistent") is not True
        or x.get("zero_backfill_enforced") is not True
        or x.get("source_status") != "AVAILABLE"
        for x in experiments
    ):
        return False, "RESEARCH_GOVERNANCE_OR_AUDIT_INVALID"

    status = maturity.get("status")
    if status == "PASS":
        if any(x.get("evidence_state") not in (
            "WAITING_FOR_POST_INCEPTION_COMPLETED_XNYS",
            "ACCUMULATING_FORWARD_EVIDENCE",
        ) or x.get("evidence_fingerprint_current") is not True
               or x.get("source_fingerprint_review_required") is not False
               for x in experiments):
            return False, "RESEARCH_PASS_INCONSISTENT"
        return True, "RESEARCH_PASS_SHADOW_ONLY"
    if status != "ATTENTION":
        return False, "RESEARCH_MATURITY_BLOCKED"
    if any(
        x.get("evidence_state") != DRIFT
        or x.get("evidence_fingerprint_audited") is not True
        or x.get("evidence_fingerprint_current") is not False
        or x.get("source_fingerprint_review_required") is not True
        or not isinstance(x.get("registered_fingerprint"), str)
        or not HEX_SHA256.fullmatch(x["registered_fingerprint"])
        or not isinstance(x.get("queue_fingerprint"), str)
        or not HEX_SHA256.fullmatch(x["queue_fingerprint"])
        or x["registered_fingerprint"] == x["queue_fingerprint"]
        for x in experiments
    ):
        return False, "UNREVIEWED_OR_UNKNOWN_RESEARCH_ATTENTION"
    # Explicitly permitting signal-only publication, NOT changing maturity status.
    return True, "RESEARCH_DRIFT_RECORDED_SHADOW_PUBLICATION_ONLY"

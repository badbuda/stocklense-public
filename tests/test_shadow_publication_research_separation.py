"""Frozen 8.0 operational signal remains publishable on EXPLICIT UNPROMOTED
research fingerprint ATTENTION, while all genuine prospective failures
still block publication. No broker, no AWS, no fabricated maturity.
"""
from copy import deepcopy
import pytest
from pipeline_validate import assess_prospective_maturity

def report(state="ATTENTION_PROSPECTIVE_EVIDENCE_FINGERPRINT_DRIFT",status="ATTENTION"):
    return {"status":status,"producer_current":True,"experiments":[{
        "experiment_id":"SL9-007-UPSHIFT-CONFIRMATION",
        "status":"ACTIVE_RESEARCH_ONLY",
        "automatic_promotion":False,
        "definition_current":True,
        "zero_backfill_enforced":True,
        "audit_schema_complete":True,
        "persistence_consistent":True,
        "evidence_state":state,
        "evidence_fingerprint_current":False,
        "evidence_fingerprint_audited":True,
        "source_fingerprint_review_required":True,
        "accepted_completed_xnys_sessions":13,
        "persisted_prospective_sessions":13,
    }]}

def test_known_unpromoted_sl9_007_fingerprint_attention_is_visible_not_a_shadow_publication_failure():
    errors,attention=assess_prospective_maturity(report())
    assert errors==[]
    assert attention==["SL9-007-UPSHIFT-CONFIRMATION"]

@pytest.mark.parametrize("field,value,code",[
    ("automatic_promotion",True,"PROSPECTIVE_UNAUTHORIZED_PROMOTION"),
    ("definition_current",False,"PROSPECTIVE_DEFINITION_DRIFT"),
    ("zero_backfill_enforced",False,"PROSPECTIVE_BACKFILL_GATE_MISSING"),
    ("audit_schema_complete",False,"PROSPECTIVE_PERSISTENCE_OR_SCHEMA_INVALID"),
    ("persistence_consistent",False,"PROSPECTIVE_PERSISTENCE_OR_SCHEMA_INVALID"),
    ("source_fingerprint_review_required",False,"PROSPECTIVE_UNQUALIFIED_ATTENTION"),
    ("evidence_fingerprint_audited",False,"PROSPECTIVE_UNQUALIFIED_ATTENTION"),
    ("evidence_fingerprint_current",True,"PROSPECTIVE_UNQUALIFIED_ATTENTION"),
])
def test_security_or_research_provenance_violation_still_blocks(field,value,code):
    x=report()
    x["experiments"][0][field]=value
    failures,_=assess_prospective_maturity(x)
    assert code in failures

def test_blocked_research_never_turns_to_pass():
    x=report("BLOCKED_MISSING_RETURNS_SOURCE","BLOCKED")
    errs,attention=assess_prospective_maturity(x)
    assert "PROSPECTIVE_MATURITY_BLOCKED" in errs
    assert attention==[]

def test_attention_cannot_be_masked_with_pass_label():
    x=report(status="PASS")
    failures,attention=assess_prospective_maturity(x)
    assert "PROSPECTIVE_ATTENTION_HIDDEN_BY_PASS" in failures
    assert attention

def test_stale_producer_blocks_even_when_evidence_is_unpromoted():
    x=report()
    x["producer_current"]=False
    failures,_=assess_prospective_maturity(x)
    assert "PROSPECTIVE_PRODUCER_STALE" in failures

def test_properly_audited_frozen_research_pass_remains_pass():
    x=report("ACCUMULATING_FORWARD_EVIDENCE","PASS")
    x["experiments"][0].update(evidence_fingerprint_current=True,
                               source_fingerprint_review_required=False)
    failures,attention=assess_prospective_maturity(x)
    assert failures==[] and attention==[]

def test_empty_or_unknown_maturity_never_passes():
    for payload in (None,{},{"status":"PASS","producer_current":True,"experiments":[]},
                    {"status":"ATTENTION","producer_current":True,"experiments":[{}]}):
        errors,_=assess_prospective_maturity(payload)
        assert errors

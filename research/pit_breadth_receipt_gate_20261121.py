"""Fail-closed external PIT receipt check. Structural only; never certifies truth."""
from datetime import datetime
import re
def ts(s):
    d=datetime.fromisoformat(s)
    if d.tzinfo is None or d.utcoffset() is None: raise ValueError("NAIVE_TIMESTAMP")
    return d
def qualify(r):
    try:
        if r["source_kind"]!="observed_pit" or r["index"]!="NDX": raise ValueError("NOT_OBSERVED_NDX")
        cutoff=ts(r["decision_at"])
        vs=r["vendors"]
        if len(vs)!=2 or vs[0]["vendor_id"]==vs[1]["vendor_id"]: raise ValueError("TWO_DISTINCT_VENDORS_REQUIRED")
        for v in vs:
            if not v["vendor_id"] or not v["source_reference"]: raise ValueError("MISSING_PROVENANCE")
            if not re.fullmatch("[0-9a-f]{64}",v["snapshot_sha256"]): raise ValueError("INVALID_HASH")
            if ts(v["published_at"])>cutoff or ts(v["retrieved_at"])<ts(v["published_at"]): raise ValueError("FUTURE_OR_INCONSISTENT_PROVENANCE")
            members=v["members"]
            if not members or len(set(members))!=len(members) or any(not isinstance(m,str) or not m.strip() for m in members): raise ValueError("INVALID_MEMBERS")
        if set(vs[0]["members"])!=set(vs[1]["members"]): raise ValueError("VENDOR_DISAGREEMENT")
        if type(r["expected_security_count"]) is not int or len(vs[0]["members"])!=r["expected_security_count"]: raise ValueError("COUNT_MISMATCH")
        return {"status":"STRUCTURAL_ONLY","historical_truth_verified":False,"independent_vendors_verified":False,"performance_verified":False,"tax_law_verified":False}
    except (KeyError,TypeError,ValueError) as e:
        return {"status":"BLOCKED","reason":str(e),"historical_truth_verified":False,"performance_verified":False,"tax_law_verified":False}

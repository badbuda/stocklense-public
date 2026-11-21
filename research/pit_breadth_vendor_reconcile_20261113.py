"""Research-only independent-vendor PIT membership reconciliation; never authorizes trading."""
from datetime import datetime, timezone

def _utc(s):
    t = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if t.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return t.astimezone(timezone.utc)

def reconcile(primary, secondary, decision_at):
    """Inputs: {vendor_id, observations:[{security_id, known_at, active}]}.
    Strict exact agreement is diagnostic, NOT proof that either vendor is correct.
    """
    try:
        decision = _utc(decision_at)
        if not primary.get("vendor_id") or not secondary.get("vendor_id"):
            raise ValueError("MISSING_VENDOR_ID")
        if primary["vendor_id"] == secondary["vendor_id"]:
            raise ValueError("SAME_VENDOR_NOT_INDEPENDENT")
        sets = []
        for feed in (primary, secondary):
            rows = feed["observations"]
            if not rows:
                raise ValueError("EMPTY_VENDOR_OBSERVATIONS")
            observed = {}
            for row in rows:
                key = row["security_id"]
                if not isinstance(key, str) or not key.strip() or key in observed:
                    raise ValueError("INVALID_OR_DUPLICATE_SECURITY_ID")
                if type(row["active"]) is not bool:
                    raise ValueError("NON_BOOLEAN_MEMBERSHIP")
                if _utc(row["known_at"]) > decision:
                    raise ValueError("FUTURE_VENDOR_DISCLOSURE")
                observed[key] = row["active"]
            sets.append(observed)
        if sets[0] != sets[1]:
            return {"status":"BLOCKED","reason":"VENDOR_MEMBERSHIP_DISAGREEMENT",
                    "only_primary":sorted(set(sets[0])-set(sets[1])),
                    "only_secondary":sorted(set(sets[1])-set(sets[0])),
                    "conflicting":sorted(k for k in sets[0].keys() & sets[1].keys()
                                         if sets[0][k] != sets[1][k]),
                    "historical_breadth_authorized":False}
        return {"status":"AGREEMENT_ONLY","count":sum(sets[0].values()),
                "historical_breadth_authorized":False,
                "reason":"INDEPENDENT_VENDOR_IDENTITY_AND_HISTORY_NOT_ATTESTED"}
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError) as e:
        return {"status":"BLOCKED","reason":str(e),"historical_breadth_authorized":False}

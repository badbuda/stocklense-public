"""Independent PIT breadth coverage qualification; research-only, fail closed.

The claimed membership source must be independently attested upstream.
This gate checks that the supplied full universe and price observations agree
for each decision; it cannot certify vendor truth or historical completeness.
"""
from datetime import datetime, date, timezone
from math import isfinite

def _ts(value):
    x = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if x.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return x.astimezone(timezone.utc)

def qualify(snapshot):
    try:
        if snapshot["source_kind"] != "observed_constituent_pit":
            raise ValueError("PROXY_NOT_PIT")
        if not snapshot.get("membership_source_id") or not snapshot.get("price_source_id"):
            raise ValueError("SOURCE_PROVENANCE_MISSING")
        decision = _ts(snapshot["decision_at"])
        session = date.fromisoformat(snapshot["session"])
        if decision.date() != session:
            raise ValueError("DECISION_SESSION_UTC_MISMATCH")
        expected = snapshot["membership"]
        observed = snapshot["prices"]
        if not expected or not observed:
            raise ValueError("EMPTY_UNIVERSE_OR_PRICES")
        membership = {}
        for item in expected:
            symbol = item["security_id"]
            if not symbol or symbol in membership:
                raise ValueError("DUPLICATE_OR_EMPTY_SECURITY_ID")
            if _ts(item["known_at"]) > decision:
                raise ValueError("FUTURE_MEMBERSHIP")
            if date.fromisoformat(item["effective_from"]) > session:
                raise ValueError("NOT_YET_EFFECTIVE")
            end = item.get("effective_to")
            if end is not None and date.fromisoformat(end) <= session:
                raise ValueError("EXPIRED_MEMBER")
            membership[symbol] = item
        prices = {}
        for item in observed:
            symbol = item["security_id"]
            if not symbol or symbol in prices:
                raise ValueError("DUPLICATE_OR_EMPTY_PRICE_ID")
            if _ts(item["known_at"]) > decision:
                raise ValueError("FUTURE_PRICE")
            if date.fromisoformat(item["session"]) != session:
                raise ValueError("STALE_OR_WRONG_SESSION_PRICE")
            px = float(item["close"])
            if not isfinite(px) or px <= 0:
                raise ValueError("INVALID_PRICE")
            prices[symbol] = px
        if set(membership) != set(prices):
            raise ValueError("MEMBERSHIP_PRICE_SET_MISMATCH")
        # A single-member synthetic fixture is still NOT a qualified historical
        # Nasdaq universe; completeness must be independently certified.
        return {"status": "STRUCTURAL_ONLY", "count": len(membership),
                "historical_breadth_authorized": False,
                "reason": "NO_INDEPENDENT_MEMBERSHIP_COMPLETENESS_ATTESTATION"}
    except (KeyError, TypeError, ValueError, OverflowError, AttributeError) as exc:
        return {"status": "BLOCKED", "reason": str(exc),
                "historical_breadth_authorized": False}

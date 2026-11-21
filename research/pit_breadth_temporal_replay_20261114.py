"""Research-only temporal eligibility gate; does not certify PIT source truth."""
from datetime import datetime, timezone

def _utc(value):
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if d.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP")
    return d.astimezone(timezone.utc)

def qualify_replay(rows):
    """Each row: decision_at, signal_known_at, order_at, fill_at, split,
    source_kind, dataset_id. No return/performance computation occurs here.
    Order and fill must be strictly after decision; split boundaries ordered.
    """
    try:
        if not rows:
            raise ValueError("EMPTY_REPLAY")
        seen = set()
        last_decision = None
        dataset = None
        last_split = -1
        rank = {"train": 0, "validation": 1, "test": 2}
        for row in rows:
            if row["source_kind"] != "observed_constituent_pit":
                raise ValueError("PROXY_OR_SYNTHETIC")
            if not row["dataset_id"]:
                raise ValueError("DATASET_ID_MISSING")
            if dataset is None:
                dataset = row["dataset_id"]
            if dataset != row["dataset_id"]:
                raise ValueError("MIXED_DATASET")
            decision = _utc(row["decision_at"])
            known = _utc(row["signal_known_at"])
            order = _utc(row["order_at"])
            fill = _utc(row["fill_at"])
            if decision in seen or (last_decision is not None and decision <= last_decision):
                raise ValueError("NON_MONOTONIC_DECISION")
            seen.add(decision)
            last_decision = decision
            if known > decision:
                raise ValueError("LOOKAHEAD_SIGNAL")
            if order <= decision or fill < order:
                raise ValueError("SAME_BAR_OR_PREORDER_FILL")
            split = rank[row["split"]]
            if split < last_split:
                raise ValueError("OOS_SPLIT_BACKTRACK")
            last_split = split
        return {"status": "TEMPORAL_ONLY", "rows": len(rows),
                "historical_breadth_authorized": False,
                "tax_validated": False,
                "performance_validated": False,
                "reason": "NO_VENDOR_ATTESTATION_OR_TAX_LEDGER"}
    except (KeyError, ValueError, TypeError, AttributeError, OverflowError) as exc:
        return {"status": "BLOCKED", "reason": str(exc),
                "historical_breadth_authorized": False}

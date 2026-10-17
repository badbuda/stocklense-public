"""SL9-033: compare TWO complete pinned ALFRED as-of envelopes offline.

This measures vintage revisions only, NOT public release time, licensed access,
historical first-seen, tradeability or alpha. No network or broker operations.
"""
from __future__ import annotations

from decimal import Decimal
from hashlib import sha256

from research_pit_json_integrity import strict_json
from research_pit_vintage_gate import BOUNDS, audit_snapshot


def _rows(raw: bytes) -> dict[str, Decimal | None]:
    env = strict_json(raw)
    return {
        row["date"]: None if row["value"] == "." else Decimal(str(row["value"]))
        for row in env["response"]["observations"]
    }


def compare_vintages(earlier_raw: bytes, later_raw: bytes, *,
                     series_id: str, decision_session: str) -> dict:
    """Reject truncated/ambiguous histories; never turn vintage dates into timestamps."""
    if series_id not in BOUNDS:
        raise ValueError("UNREGISTERED_VINTAGE_SERIES")
    first = audit_snapshot(earlier_raw, trade_date=decision_session,
                           expected_series=series_id)
    second = audit_snapshot(later_raw, trade_date=decision_session,
                            expected_series=series_id)
    if first["asof_date"] >= second["asof_date"]:
        raise ValueError("VINTAGES_NOT_STRICTLY_ORDERED")
    older = _rows(earlier_raw)
    newer = _rows(later_raw)
    disappeared = sorted(set(older) - set(newer))
    if disappeared:
        raise ValueError("VINTAGE_HISTORY_TRUNCATED_OR_REMOVED:" + disappeared[0])
    shared = sorted(set(older) & set(newer))
    changed = [d for d in shared if older[d] != newer[d]]
    revised = [d for d in changed if older[d] is not None and newer[d] is not None]
    filled = [d for d in changed if older[d] is None and newer[d] is not None]
    became_missing = [d for d in changed if older[d] is not None and newer[d] is None]
    added = sorted(set(newer) - set(older))
    return {
        "kind": "SL9_033_ALFRED_VINTAGE_DELTA_FEASIBILITY",
        "status": "BLOCKED_NO_INDEPENDENT_RELEASE_CLOCK_OR_ORIGIN_RECEIPT",
        "series_id": series_id,
        "decision_session": decision_session,
        "earlier_asof_date": first["asof_date"],
        "later_asof_date": second["asof_date"],
        "earlier_raw_sha256": sha256(earlier_raw).hexdigest(),
        "later_raw_sha256": sha256(later_raw).hexdigest(),
        "earlier_observation_rows": len(older),
        "later_observation_rows": len(newer),
        "overlapping_observations": len(shared),
        "changed_overlap_values": len(changed),
        "revised_numeric_values": len(revised),
        "filled_missing_values": len(filled),
        "became_missing_values": len(became_missing),
        "new_observations": len(added),
        "truncated_observations": 0,
        "revision_dates": revised,
        "new_observation_dates": added,
        "release_time_verified": False,
        "first_seen_independently_certified": False,
        "ice_license_verified": False,
        "eligible_tradable_rows": 0,
        "historical_sample_reused": True,
        "frozen_stocklens8_changed": False,
        "broker_orders_authorized": False,
        "automatic_promotion": False,
    }

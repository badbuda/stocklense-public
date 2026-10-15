"""SL9-031: causal as-of source gates, never independently certified first-seen."""
from __future__ import annotations
from datetime import timedelta, timezone
from hashlib import sha256
import json
import exchange_calendars as xcals
from research_cross_calendar_gate import NY, _parse_utc, sec_dissemination_lower_bound
from research_pit_quote_gate import audit as audit_quote
from research_pit_vintage_gate import audit_snapshot

def decision_0931(stamp):
    t = _parse_utc(stamp)
    session = t.astimezone(NY).date().isoformat()
    cal = xcals.get_calendar("XNYS")
    if not cal.is_session(session):
        raise ValueError("DECISION_NOT_XNYS_SESSION")
    op = cal.session_open(session).to_pydatetime().astimezone(timezone.utc)
    if not op + timedelta(minutes=1) <= t < op + timedelta(minutes=2):
        raise ValueError("DECISION_NOT_0931_ET")
    return t, session

def before_decision(stamp, decision):
    t = _parse_utc(stamp)
    if t >= decision:
        raise ValueError("RECEIPT_NOT_BEFORE_DECISION")
    return t

def macro_candidate(raw, *, series_id, decision_at_utc, collector_received_at_utc,
                    claimed_first_seen=False):
    decision, session = decision_0931(decision_at_utc)
    receipt = before_decision(collector_received_at_utc, decision)
    parsed = audit_snapshot(raw, trade_date=session, expected_series=series_id)
    if receipt.astimezone(NY).date().isoformat() < parsed["asof_date"]:
        raise ValueError("RECEIPT_BEFORE_CLAIMED_VINTAGE")
    last = json.loads(raw)["response"]["observations"][-1]
    missing = last["value"] == "."
    return {"kind": "SL9_031_MACRO_ASOF_CANDIDATE", "series_id": series_id,
        "session": session, "vintage_date": parsed["asof_date"],
        "latest_observation_date": last["date"], "latest_missing": missing,
        "raw_sha256": sha256(raw).hexdigest(),
        "status": "BLOCKED_MISSING_LATEST_VALUE" if missing else "BLOCKED_NO_INDEPENDENT_RELEASE_CLOCK",
        "claimed_first_seen_ignored": bool(claimed_first_seen),
        "independent_first_seen_proven": False, "licensed_ice_history_proven": False,
        "qualified_rows": 0, "frozen_8_changed": False,
        "capital_authorized": False}

def sec_candidate(*, form, started_at_utc, accepted_at_utc,
                  collector_received_at_utc, decision_at_utc,
                  claimed_first_seen=False):
    decision, session = decision_0931(decision_at_utc)
    accepted = _parse_utc(accepted_at_utc)
    receipt = before_decision(collector_received_at_utc, decision)
    if receipt < accepted:
        raise ValueError("SEC_RECEIPT_BEFORE_ACCEPTANCE")
    floor = sec_dissemination_lower_bound(
        form=form, transmission_started_at_utc=started_at_utc,
        accepted_at_utc=accepted_at_utc)
    if receipt.astimezone(NY).date().isoformat() < floor["earliest_possible_date"]:
        raise ValueError("SEC_RECEIPT_BEFORE_EARLIEST_PUBLIC_DAY")
    return {"kind": "SL9_031_SEC_CANDIDATE", "session": session,
        "earliest_possible_date": floor["earliest_possible_date"],
        "status": "BLOCKED_NO_INDEPENDENT_PUBLIC_FIRST_SEEN",
        "claimed_first_seen_ignored": bool(claimed_first_seen),
        "qualified_rows": 0, "capital_authorized": False}

def gdelt_candidate(*, article_published_at_utc, batch_at_utc,
                    collector_received_at_utc, decision_at_utc,
                    claimed_first_seen=False):
    decision, session = decision_0931(decision_at_utc)
    published = _parse_utc(article_published_at_utc)
    batch = _parse_utc(batch_at_utc)
    receipt = before_decision(collector_received_at_utc, decision)
    if batch < published:
        raise ValueError("GDELT_BATCH_BEFORE_ARTICLE")
    if receipt < batch:
        raise ValueError("GDELT_RECEIPT_BEFORE_BATCH")
    return {"kind": "SL9_031_GDELT_CANDIDATE", "session": session,
        "status": "BLOCKED_NO_INDEPENDENT_BATCH_FIRST_SEEN",
        "article_time_used_as_first_seen": False,
        "claimed_first_seen_ignored": bool(claimed_first_seen),
        "qualified_rows": 0, "capital_authorized": False}

def quote_capacity_candidate(*, quote, side, shares, decision_at_utc):
    decision, session = decision_0931(decision_at_utc)
    if side not in ("BUY", "SELL") or type(shares) is not int or shares <= 0:
        raise ValueError("INVALID_HYPOTHETICAL_ORDER")
    audit_quote(json.dumps([quote], sort_keys=True, allow_nan=False).encode())
    age = (decision - _parse_utc(quote["timestamp_utc"])).total_seconds()
    if not 0 <= age <= 1:
        raise ValueError("NBBO_FUTURE_OR_STALE")
    depth = quote["ask_size"] if side == "BUY" else quote["bid_size"]
    return {"kind": "SL9_031_QUOTE_SIZE_CANDIDATE", "session": session,
        "symbol": quote["symbol"], "side": side,
        "requested_shares": shares, "displayed_shares": depth,
        "hypothetical_shares_at_one_displayed_quote": min(shares, depth),
        "displayed_size_covers_request": depth >= shares,
        "quote_age_ms": round(age * 1000, 3),
        "status": "BLOCKED_NO_INDEPENDENT_SIP_OR_BROKER_FILL",
        "actual_broker_fills_verified": 0, "capital_authorized": False}

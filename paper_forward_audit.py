"""Prospective paper capture quality gate. Never fabricates missed fills."""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def expected_exchange_sessions(previous_asof: str, current_asof: str) -> list[str]:
    """Calendar-derived completed exchange dates, never weekend/holiday guesses."""
    import exchange_calendars as xcals
    cal = xcals.get_calendar("XNYS")
    sessions = cal.sessions_in_range(previous_asof, current_asof)
    return [str(s.date()) for s in sessions if str(s.date()) > previous_asof]


def read_json(path):
    p = Path(path)
    return json.loads(p.read_text()) if p.is_file() else None


def rows(path):
    p = Path(path)
    if not p.is_file():
        return []
    with p.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def evaluate(*, current, prior, ledger, gaps, snapshots, state=None):
    errors = []
    asof = (current or {}).get("latest", {}).get("asof_date")
    previous_asof = (prior or {}).get("latest", {}).get("asof_date")
    if not asof or not previous_asof or asof < previous_asof:
        errors.append("SIGNAL_SESSION_ORDER_INVALID")
    paper_dates = [x.get("session_date") for x in ledger]
    gap_dates = [x.get("session_date") for x in gaps]
    if any(not x for x in paper_dates + gap_dates):
        errors.append("MISSING_EVIDENCE_SESSION")
    if len(set(paper_dates)) != len(paper_dates) or paper_dates != sorted(paper_dates):
        errors.append("DUPLICATE_OR_NONMONOTONE_PAPER_LEDGER")
    if set(paper_dates) & set(gap_dates):
        errors.append("PAPER_AND_MISSED_SESSION_CONFLICT")
    if len(set(gap_dates)) != len(gap_dates) or gap_dates != sorted(gap_dates):
        errors.append("DUPLICATE_OR_NONMONOTONE_EVIDENCE_GAPS")
    if previous_asof and asof and asof > previous_asof:
        try:
            expected = expected_exchange_sessions(previous_asof, asof)
        except (ValueError, TypeError, OverflowError):
            errors.append("EXCHANGE_CALENDAR_RANGE_INVALID")
            expected = []
        observed = set(paper_dates) | set(gap_dates)
        if any(session not in observed for session in expected):
            errors.append("UNACCOUNTED_COMPLETED_EXCHANGE_SESSIONS")
        if any(session not in expected for session in observed if session > previous_asof):
            errors.append("EVIDENCE_SESSION_NOT_ON_EXCHANGE_CALENDAR")
    if paper_dates and (not state or state.get("last_mark_session") != paper_dates[-1]):
        errors.append("LATEST_PAPER_STATE_NOT_RECONCILED")
    for r in ledger:
        session = r.get("session_date", "")
        signal_date = r.get("signal_date", "")
        if not signal_date or signal_date >= session:
            errors.append("LOOKAHEAD_OR_SAME_SESSION_FILL")
            continue
        persisted = snapshots.get(signal_date) or {}
        generated = persisted.get("generated_at_utc")
        if not generated:
            errors.append("PAPER_SIGNAL_SNAPSHOT_MISSING")
            continue
        try:
            t = datetime.fromisoformat(str(generated).replace("Z", "+00:00"))
            if t.tzinfo is None:
                raise ValueError("timestamp is naive")
            market_open = datetime.combine(date.fromisoformat(session), time(9, 30),
                                           tzinfo=NY)
            if t.astimezone(timezone.utc) >= market_open.astimezone(timezone.utc):
                errors.append("SIGNAL_GENERATED_AFTER_PAPER_SESSION_OPEN")
        except ValueError:
            errors.append("BAD_PAPER_SIGNAL_TIMESTAMP")
    if previous_asof and asof and asof > previous_asof:
        if asof not in paper_dates and asof not in gap_dates:
            errors.append("ADVANCED_MARKET_SESSION_WITHOUT_PAPER_OR_EXPLICIT_GAP")
    missing = sorted(set(gap_dates))
    result = {
        "schema_version": 1,
        "status": "FAIL" if errors else ("MISSED_EXECUTION_REVIEW" if missing else
                                        "PROSPECTIVE_PAPER_ACTIVE" if paper_dates else
                                        "WAITING_FOR_NEXT_COMPLETED_SESSION"),
        "current_signal_date": asof,
        "persisted_signal_date": previous_asof,
        "paper_sessions": len(paper_dates),
        "explicit_missed_sessions": len(missing),
        "errors": sorted(set(errors)),
        "live_trading_authorized": False,
        "backfill_authorized": False,
        "claim": "A waiting status is not execution evidence; absent paper sessions never become simulated historical fills.",
    }
    return result


def audit(output="docs/paper_forward_audit.json"):
    current = read_json("output/latest_signal.json")
    prior = read_json("shadow_history/latest.json")
    ledger = rows("paper_portfolio/ledger.csv")
    gaps = rows("paper_portfolio/evidence_gaps.csv")
    shots = {}
    for row in ledger:
        key = row.get("signal_date")
        if key and key not in shots:
            shots[key] = read_json(f"shadow_history/{key}.json")
    result = evaluate(current=current, prior=prior, ledger=ledger, gaps=gaps,
                      snapshots=shots, state=read_json("paper_portfolio/state.json"))
    out = Path(output);out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    if result["status"] == "FAIL":
        raise RuntimeError("PAPER_FORWARD_CAPTURE_INVALID:" + ",".join(result["errors"]))
    print(json.dumps(result))
    return result


if __name__ == "__main__":
    audit()

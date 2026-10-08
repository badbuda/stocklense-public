from datetime import datetime, timezone, timedelta
from paper_forward_audit import evaluate


def report(day, generated=None):
    return {"latest": {"asof_date": day},
            "generated_at_utc": generated or "2026-10-08T11:00:00Z"}


def test_legitimate_wait_for_next_completed_session():
    r = evaluate(current=report("2026-10-07"), prior=report("2026-10-07"),
                 ledger=[], gaps=[], snapshots={}, state=None)
    assert r["status"] == "WAITING_FOR_NEXT_COMPLETED_SESSION"
    assert r["paper_sessions"] == 0
    assert r["live_trading_authorized"] is False


def test_silent_lost_execution_is_error():
    r = evaluate(current=report("2026-10-08"), prior=report("2026-10-07"),
                 ledger=[], gaps=[], snapshots={}, state=None)
    assert r["status"] == "FAIL"
    assert "ADVANCED_MARKET_SESSION_WITHOUT_PAPER_OR_EXPLICIT_GAP" in r["errors"]


def test_explicit_miss_not_backfilled():
    gaps = [{"session_date": "2026-10-08", "status": "MISSED_NO_BACKFILL"}]
    r = evaluate(current=report("2026-10-08"), prior=report("2026-10-07"),
                 ledger=[], gaps=gaps, snapshots={}, state=None)
    assert r["status"] == "MISSED_EXECUTION_REVIEW"
    assert r["paper_sessions"] == 0
    assert r["backfill_authorized"] is False


def test_one_forward_paper_fill_is_verified():
    ledger = [{"session_date": "2026-10-08", "signal_date": "2026-10-07"}]
    r = evaluate(current=report("2026-10-08"), prior=report("2026-10-07"),
                 ledger=ledger, gaps=[],
                 snapshots={"2026-10-07": report("2026-10-07", "2026-10-08T12:00:00Z")},
                 state={"last_mark_session": "2026-10-08"})
    assert r["status"] == "PROSPECTIVE_PAPER_ACTIVE"
    assert r["paper_sessions"] == 1


def test_lookahead_and_late_snapshot_fail():
    ledger = [{"session_date": "2026-10-08", "signal_date": "2026-10-07"}]
    r = evaluate(current=report("2026-10-08"), prior=report("2026-10-07"),
                 ledger=ledger, gaps=[],
                 snapshots={"2026-10-07": report("2026-10-07", "2026-10-08T17:00:00Z")},
                 state={"last_mark_session": "2026-10-08"})
    assert "SIGNAL_GENERATED_AFTER_PAPER_SESSION_OPEN" in r["errors"]


def test_rejects_state_drift_duplicates_and_same_day_fills():
    ledger = [{"session_date": "2026-10-08", "signal_date": "2026-10-08"},
              {"session_date": "2026-10-08", "signal_date": "2026-10-07"}]
    r = evaluate(current=report("2026-10-08"), prior=report("2026-10-07"),
                 ledger=ledger, gaps=[], snapshots={}, state={"last_mark_session": "2026-10-07"})
    assert "DUPLICATE_OR_NONMONOTONE_PAPER_LEDGER" in r["errors"]
    assert "LOOKAHEAD_OR_SAME_SESSION_FILL" in r["errors"]
    assert "LATEST_PAPER_STATE_NOT_RECONCILED" in r["errors"]

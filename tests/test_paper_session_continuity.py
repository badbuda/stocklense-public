"""Paper execution evidence must be complete and honest across skipped sessions."""
from __future__ import annotations

import csv
import json
from types import SimpleNamespace

import pytest

import paper_portfolio
from paper_forward_audit import evaluate, expected_exchange_sessions
from stocklens.paper import PaperIntegrityError


def _report(day, generated):
    return {"latest": {"asof_date": day}, "generated_at_utc": generated}


def _setup(monkeypatch, tmp_path, *, current_day="2026-10-08",
           previous_day="2026-10-07", existing_state=None):
    folder = tmp_path / "paper"
    folder.mkdir()
    monkeypatch.setattr(paper_portfolio, "STATE_DIR", folder)
    for name, filename in (
        ("STATE_PATH", "state.json"),
        ("LEDGER_PATH", "ledger.csv"),
        ("TRADES_PATH", "trades.csv"),
        ("LATEST_MD_PATH", "latest.md"),
        ("GAPS_PATH", "evidence_gaps.csv"),
    ):
        monkeypatch.setattr(paper_portfolio, name, folder / filename)
    current = tmp_path / "current.json"
    prior = tmp_path / "previous.json"
    current.write_text(json.dumps(_report(current_day, "2026-10-08T23:00:00Z")))
    prior.write_text(json.dumps(_report(previous_day, "2026-10-08T15:00:00Z")))
    if existing_state is not None:
        paper_portfolio.STATE_PATH.write_text(json.dumps(existing_state))
    return current, prior, folder


def test_late_bootstrap_signal_is_explicitly_missed_and_idempotent(monkeypatch, tmp_path):
    current, prior, folder = _setup(monkeypatch, tmp_path)
    monkeypatch.setattr(
        paper_portfolio, "fetch_execution_market",
        lambda _p, _c: SimpleNamespace(session_date="2026-10-08"),
    )
    for _ in range(2):
        result = paper_portfolio.reconcile(str(current), str(prior))
        assert result["paper_updated"] == "false"
        assert result["paper_status"] == "MISSED_LATE_SIGNAL_RECORDED_NO_BACKFILL"
    with (folder / "evidence_gaps.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == 1
    assert rows[0]["session_date"] == "2026-10-08"
    assert not (folder / "ledger.csv").exists()


def test_missing_nonbootstrap_session_is_recorded_without_backfill(monkeypatch, tmp_path):
    current, prior, folder = _setup(
        monkeypatch, tmp_path, current_day="2026-10-09",
        existing_state={"last_executed_signal_date": "2026-10-06"},
    )

    def missed(_p, _c):
        raise PaperIntegrityError(
            "MISSED_SHADOW_SESSION:expected_execution=2026-10-08:"
            "current_completed=2026-10-09"
        )

    monkeypatch.setattr(paper_portfolio, "fetch_execution_market", missed)
    outcome = paper_portfolio.reconcile(str(current), str(prior))
    assert outcome["paper_status"] == "MISSED_SESSION_RECORDED_NO_BACKFILL"
    with (folder / "evidence_gaps.csv").open(newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["session_date"] for r in rows] == ["2026-10-08", "2026-10-09"]
    assert not (folder / "ledger.csv").exists()


def test_exchange_calendar_requires_every_completed_trading_day():
    assert expected_exchange_sessions("2026-10-07", "2026-10-09") == [
        "2026-10-08", "2026-10-09"
    ]
    current = _report("2026-10-09", "2026-10-09T22:00:00Z")
    prior = _report("2026-10-07", "2026-10-07T22:00:00Z")
    only_recent = [{"session_date": "2026-10-09"}]
    incomplete = evaluate(
        current=current, prior=prior, ledger=[], gaps=only_recent,
        snapshots={}, state=None,
    )
    assert "UNACCOUNTED_COMPLETED_EXCHANGE_SESSIONS" in incomplete["errors"]
    complete = evaluate(
        current=current, prior=prior, ledger=[],
        gaps=[{"session_date": "2026-10-08"}, *only_recent],
        snapshots={}, state=None,
    )
    assert complete["status"] == "MISSED_EXECUTION_REVIEW"
    assert complete["explicit_missed_sessions"] == 2


def test_duplicate_gap_and_nonexchange_gap_are_rejected():
    current = _report("2026-10-09", "2026-10-09T22:00:00Z")
    prior = _report("2026-10-07", "2026-10-07T22:00:00Z")
    evidence = [{"session_date": "2026-10-08"}, {"session_date": "2026-10-08"},
                {"session_date": "2026-10-09"}]
    result = evaluate(
        current=current, prior=prior, ledger=[], gaps=evidence,
        snapshots={}, state=None,
    )
    assert "DUPLICATE_OR_NONMONOTONE_EVIDENCE_GAPS" in result["errors"]


def test_yahoo_eight_day_limit_no_longer_hides_missed_oct_sessions(monkeypatch, tmp_path):
    current, prior, folder = _setup(monkeypatch, tmp_path,
        previous_day="2026-10-09", current_day="2026-10-19",
        existing_state={"last_executed_signal_date":"2026-10-08",
                        "last_mark_session":"2026-10-09"})
    def must_never_call_yahoo(*_args):
        raise AssertionError("HISTORICAL_MINUTE_DOWNLOAD_FORBIDDEN")
    monkeypatch.setattr(paper_portfolio,"fetch_execution_market",must_never_call_yahoo)
    first=paper_portfolio.reconcile(str(current),str(prior))
    second=paper_portfolio.reconcile(str(current),str(prior))
    assert first==second
    assert first["paper_status"]=="MISSED_SESSION_RECORDED_NO_BACKFILL"
    assert first["missed_sessions_count"]=="6"
    with (folder/"evidence_gaps.csv").open(newline="") as fh:
        rows=list(csv.DictReader(fh))
    assert [x["session_date"] for x in rows]==[
        "2026-10-12","2026-10-13","2026-10-14",
        "2026-10-15","2026-10-16","2026-10-19"]
    assert all(x["status"]=="MISSED_NO_BACKFILL" for x in rows)
    assert not (folder/"ledger.csv").exists()
    assert not (folder/"trades.csv").exists()


def test_previous_paper_mark_cannot_be_skipped_when_signals_resume(monkeypatch,tmp_path):
    current,prior,folder=_setup(monkeypatch,tmp_path,
        previous_day="2026-10-19",current_day="2026-10-20",
        existing_state={"last_executed_signal_date":"2026-10-08",
                        "last_mark_session":"2026-10-09"})
    monkeypatch.setattr(paper_portfolio,"fetch_execution_market",
                        lambda *_:pytest.fail("NO_RESTART_FROM_STALE_BOOK"))
    result=paper_portfolio.reconcile(str(current),str(prior))
    assert result["paper_status"]=="MISSED_SESSION_RECORDED_NO_BACKFILL"
    with (folder/"evidence_gaps.csv").open(newline="") as fh:
        rows=list(csv.DictReader(fh))
    assert [x["session_date"] for x in rows]==[
        "2026-10-12","2026-10-13","2026-10-14","2026-10-15",
        "2026-10-16","2026-10-19","2026-10-20"]
    assert not (folder/"state.json").read_text().startswith('{"last_mark_session":')
    assert not (folder/"ledger.csv").exists()


def test_account_ahead_of_prior_signal_fails_closed(monkeypatch,tmp_path):
    current,prior,folder=_setup(monkeypatch,tmp_path,
        previous_day="2026-10-07",current_day="2026-10-08",
        existing_state={"last_executed_signal_date":"2026-10-06",
                        "last_mark_session":"2026-10-08"})
    monkeypatch.setattr(paper_portfolio,"fetch_execution_market",
                        lambda *_:pytest.fail("OUT_OF_ORDER_MARK_FORBIDDEN"))
    with pytest.raises(PaperIntegrityError,match="PAPER_BOOK_AHEAD_OF_PREVIOUS_SIGNAL"):
        paper_portfolio.reconcile(str(current),str(prior))
    assert not (folder/"ledger.csv").exists()

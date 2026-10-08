"""Falsification tests for observed-ETF replay: no future prices or synthetic P&L.

The fabricated inputs here are ONLY test fixtures. Published performance
continues to require actual observed historical QQQ/TQQQ adjusted OHLC.
"""
from __future__ import annotations

from datetime import date, timedelta
import hashlib

import pytest

from tradable_tqqq_execution_comparison import run_execution, archive_observed_adjusted_prices


@pytest.fixture(scope="module")
def market():
    qqq, tqqq = {}, {}
    day = date(2008, 1, 2)
    idx = 0
    while len(qqq) < 4300:
        if day.weekday() < 5:
            d = day.isoformat()
            qqq[d] = {"open": 50.0 * 1.00012 ** idx,
                      "close": 50.0 * 1.00012 ** idx * 1.001}
            if d >= "2010-02-09":
                tqqq[d] = {"open": 5.0 * 1.00021 ** idx,
                           "close": 5.0 * 1.00021 ** idx * 1.003}
            idx += 1
        day += timedelta(days=1)
    return qqq, tqqq


def test_full_nav_evidence_is_prior_signal_only(market):
    qqq, tqqq = market
    signals = {d: 3.0 for d in qqq}
    result = run_execution(qqq, tqqq, signals, include_daily_path=True)
    path = result["daily_nav_rows"]
    assert len(path) == result["sessions"]
    assert path[0]["date"] == result["start"]
    assert path[-1]["date"] == result["end"]
    assert path[-1]["stocklens_nav"] == result["stocklens"]["ending_equity"]
    assert path[-1]["qqq_nav"] == result["qqq_buy_hold"]["ending_equity"]
    assert all(r["effective_prior_signal_date"] < r["date"] for r in path)
    assert all(r["leverage"] == 3.0 for r in path)
    assert result["stocklens"]["ending_shares"]["QQQ"] == 0
    assert result["stocklens"]["ending_shares"]["TQQQ"] > 0


def test_midseries_future_signal_cannot_change_past_nav(market):
    qqq, tqqq = market
    labels = sorted(qqq)
    date_changed = labels[-900]
    before = run_execution(qqq, tqqq, {d: 3.0 for d in qqq},
                           include_daily_path=True)["daily_nav_rows"]
    amended = {d: 3.0 if d < date_changed else 0.0 for d in qqq}
    after = run_execution(qqq, tqqq, amended,
                          include_daily_path=True)["daily_nav_rows"]
    before_by_date = {x["date"]: x for x in before}
    after_by_date = {x["date"]: x for x in after}
    assert any(before_by_date[d]["stocklens_nav"] != after_by_date[d]["stocklens_nav"]
               for d in before_by_date if d > date_changed)
    for d in before_by_date:
        if d <= date_changed:
            assert before_by_date[d] == after_by_date[d]


def test_future_tqqq_shock_changes_only_that_session_and_later(market):
    qqq, tqqq = market
    signals = {d: 3.0 for d in qqq}
    before = run_execution(qqq, tqqq, signals,
                           include_daily_path=True)["daily_nav_rows"]
    target = before[-75]["date"]
    patched = {d: dict(values) for d, values in tqqq.items()}
    patched[target]["close"] *= 0.9
    after = run_execution(qqq, patched, signals,
                          include_daily_path=True)["daily_nav_rows"]
    for a, b in zip(before, after):
        assert a["date"] == b["date"]
        assert a["qqq_nav"] == b["qqq_nav"]
        if a["date"] < target:
            assert a == b
    assert before[-75]["stocklens_nav"] != after[-75]["stocklens_nav"]


@pytest.mark.parametrize("level", [1.25, 2.0])
def test_intermediate_levels_are_actual_qqq_tqqq_blends(market, level):
    qqq, tqqq = market
    signals = {d: level for d in qqq}
    base = run_execution(qqq, tqqq, signals)
    assert base["stocklens"]["ending_shares"]["QQQ"] > 0
    assert base["stocklens"]["ending_shares"]["TQQQ"] > 0
    assert base["stocklens"]["ending_cash"] >= 0
    revised = {d: dict(row) for d, row in tqqq.items()}
    end = base["end"]
    revised[end]["close"] *= 0.5
    damaged = run_execution(qqq, revised, signals)
    assert damaged["stocklens"]["ending_equity"] < base["stocklens"]["ending_equity"]
    assert damaged["qqq_buy_hold"]["ending_equity"] == base["qqq_buy_hold"]["ending_equity"]


def test_missing_midseries_tqqq_is_blocker_not_qqq_times_three(market):
    qqq, tqqq = market
    damaged = dict(tqqq)
    damaged.pop(list(tqqq)[1000])
    with pytest.raises(ValueError, match="MISSING_TQQQ_TRADING_SESSIONS"):
        run_execution(qqq, damaged, {d: 3.0 for d in qqq})


def test_monthly_contribution_ledger_is_matched_and_never_cagr(market):
    qqq, tqqq = market
    result = run_execution(qqq, tqqq, {d: 3.0 for d in qqq},
                           monthly=3500.0, include_daily_path=True)
    rows = result["daily_nav_rows"]
    deposit = sum(float(x["contribution"]) for x in rows)
    assert deposit > 0
    assert result["stocklens"]["paid_capital"] == pytest.approx(100000 + deposit)
    assert result["qqq_buy_hold"]["paid_capital"] == result["stocklens"]["paid_capital"]
    assert result["stocklens"]["cagr_without_contributions"] is None
    assert result["qqq_buy_hold"]["cagr_without_contributions"] is None
    months = [r["date"][:7] for r in rows]
    assert all(r["contribution"] == (3500 if months[i] != months[i-1] else 0)
               for i, r in enumerate(rows) if i > 0)



def test_adjusted_etf_prices_are_preserved_verbatim_in_auditable_snapshot(market, tmp_path):
    qqq, tqqq = market
    dest = tmp_path / "observed_etfs.csv"
    evidence = archive_observed_adjusted_prices(qqq, tqqq, str(dest))
    assert evidence["rows"] > 3000
    assert evidence["kind"] == "DERIVED_YAHOO_AUTO_ADJUSTED_OPEN_CLOSE"
    assert evidence["independent_vendor_verified"] is False
    assert evidence["raw_unadjusted_exchange_prices"] is False
    assert evidence["sha256"] == hashlib.sha256(dest.read_bytes()).hexdigest()
    rows = dest.read_text().splitlines()
    assert len(rows) == evidence["rows"] + 1
    assert rows[1].startswith(evidence["first_date"] + ",")
    assert rows[-1].startswith(evidence["last_date"] + ",")
    assert "tqqq_adjusted_open" in rows[0]

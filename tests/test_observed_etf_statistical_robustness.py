"""Fixture-only tests. Fabricated NAV values never enter published performance."""
from __future__ import annotations

from datetime import date, timedelta
import copy

import pytest

from observed_etf_statistical_robustness import evaluate, _block_bootstrap


def report_example():
    start = date(2011, 1, 3)
    dates = []
    current = start
    while len(dates) < 1320:
        if current.weekday() < 5:
            dates.append(current.isoformat())
        current += timedelta(days=1)
    s = q = 100_000.0
    nav = []
    for i, d in enumerate(dates):
        if i:
            s *= 1.0005 + (0.004 if i % 17 == 0 else -0.0002)
            q *= 1.0004 + (0.003 if i % 19 == 0 else -0.0001)
        nav.append({
            "date": d,
            "effective_prior_signal_date": (date.fromisoformat(d) - timedelta(days=1)).isoformat(),
            "stocklens_nav": round(s, 6), "qqq_nav": round(q, 6)
        })
    return {
        "kind": "OBSERVED_QQQ_TQQQ_DAILY_OPEN_EXECUTION_PROXY",
        "observed_instruments": ["QQQ", "TQQQ"],
        "full_lean_execution_parity": False,
        "automatic_model_promotion": False,
        "price_fingerprint_sha256": "a" * 64,
        "period": {"start": dates[0], "end": dates[-1], "sessions": len(nav)},
        "no_contributions": {
            "start": dates[0], "end": dates[-1], "sessions": len(nav),
            "monthly_contribution": 0,
            "stocklens": {"paid_capital": 100000.0},
            "qqq_buy_hold": {"paid_capital": 100000.0},
            "ending_equity_ratio": nav[-1]["stocklens_nav"] / nav[-1]["qqq_nav"],
            "daily_nav_rows": nav
        }
    }


def test_reproducible_block_resampling_and_provenance():
    r = report_example()
    a = evaluate(r, bootstrap_reps=35)
    b = evaluate(r, bootstrap_reps=35)
    assert a == b
    assert a["synthetic_leverage_used"] is False
    assert a["clean_out_of_sample_test"] is False
    assert a["statistical_significance_proven"] is False
    assert set(a["paired_moving_block_bootstrap"]) == {"21", "63", "126"}
    assert a["daily_relative_log_observations"] == 1320
    assert a["original_relative_ending_wealth_ratio"] == pytest.approx(
        r["no_contributions"]["ending_equity_ratio"], rel=1e-6
    )
    assert all(0 <= x["fraction_resamples_above_zero_NOT_P_VALUE"] <= 1
               for x in a["paired_moving_block_bootstrap"].values())


def test_later_price_change_recalculates_evidence_fingerprint():
    a = report_example()
    b = copy.deepcopy(a)
    last = b["no_contributions"]["daily_nav_rows"][-1]
    last["stocklens_nav"] *= 0.9
    b["no_contributions"]["ending_equity_ratio"] = last["stocklens_nav"] / last["qqq_nav"]
    before = evaluate(a, bootstrap_reps=7)
    after = evaluate(b, bootstrap_reps=7)
    assert before["full_nav_sha256"] != after["full_nav_sha256"]
    assert before["original_relative_ending_wealth_ratio"] != after["original_relative_ending_wealth_ratio"]


def test_unsorted_date_and_lookahead_blocked():
    a = report_example()
    a["no_contributions"]["daily_nav_rows"][800]["date"] = a["no_contributions"]["daily_nav_rows"][799]["date"]
    with pytest.raises(ValueError, match="NONMONOTONIC_DAILY_DATES"):
        evaluate(a, bootstrap_reps=7)
    b = report_example()
    b["no_contributions"]["daily_nav_rows"][400]["effective_prior_signal_date"] = b["no_contributions"]["daily_nav_rows"][400]["date"]
    with pytest.raises(ValueError, match="LOOKAHEAD_AT_SESSION_MARK"):
        evaluate(b, bootstrap_reps=7)


def test_incomplete_or_nonobserved_paths_are_rejected():
    a = report_example()
    a["observed_instruments"] = ["QQQ"]
    with pytest.raises(ValueError, match="SOURCE_NOT_OBSERVED"):
        evaluate(a, bootstrap_reps=7)
    b = report_example()
    b["no_contributions"]["daily_nav_rows"] = b["no_contributions"]["daily_nav_rows"][:-3]
    with pytest.raises(ValueError, match="MISSING_COMPLETE_OBSERVED_DAILY_PATH"):
        evaluate(b, bootstrap_reps=7)


def test_bootstrap_requires_two_full_blocks():
    with pytest.raises(ValueError, match="INSUFFICIENT_SESSIONS"):
        _block_bootstrap([0.01] * 10, width=21, repeats=5, seed=1)

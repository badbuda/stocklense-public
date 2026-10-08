from copy import deepcopy

from model_readiness_audit import evaluate


def fixture():
    period = {"start": "2010-02-11", "end": "2026-10-07", "sessions": 4189}
    summary = {"start": period["start"], "end": period["end"],
               "stocklens": {"paid_capital": 100000, "ending_equity": 2000000,
                             "cagr_without_contributions": 0.2, "max_drawdown": -0.5},
               "qqq_buy_hold": {"paid_capital": 100000, "ending_equity": 500000,
                                "cagr_without_contributions": 0.1, "max_drawdown": -0.3}}
    return dict(
        report={"period": period, "status": "PASS",
                "observed_instruments": ["QQQ", "TQQQ"],
                "price_source": "YFINANCE_AUTO_ADJUSTED_DAILY_OPEN_AND_CLOSE",
                "price_fingerprint_sha256": "a" * 64,
                "no_contributions": summary,
                "initial_100k_monthly_3500": {
                    "stocklens": {"paid_capital": 800000},
                    "qqq_buy_hold": {"paid_capital": 800000}},
                "slippage_stress_no_contributions": [{}] * 5,
                "signal_lag_stress_no_contributions": [{}] * 3,
                "intraday_0931_0932_fills_observed": False,
                "baseline": "StockLens 8.0 FROZEN"},
        policy={"never_fallback_to_synthetic": True},
        capital={"prospective_completed_sessions": 8, "scaled_capital_ready": False},
        benchmark={"status": "WAITING_FOR_PROSPECTIVE_DATA", "sessions": 0},
        paper_gap={"status": "WAITING_FOR_PAIRED_EVIDENCE", "paper_sessions": 0,
                   "paired_sessions": 0},
        workbench={"full_lean_export": {"status": "MISSING",
                                      "execution_parity_ready": False,
                                      "errors": ["DAILY_MISSING", "ORDERS_MISSING"]}},
        observation={},
        health={"status": "HEALTHY", "market_session_freshness": "CURRENT",
                "market_session": {"signal_replay_aligned": True}},
        source_proof={},
    )


def test_valid_backtest_does_not_approve_live():
    result = evaluate(**fixture())
    assert result["status"] == "BLOCKED_FOR_LIVE_TRADING"
    assert result["automated_live_trading_authorized"] is False
    assert result["automatic_model_promotion"] is False
    assert result["passed_count"] >= 3
    assert "LIVE_EXECUTION_TIME_PARITY" in result["blockers"]
    assert "RAW_LEAN_SAME_RUN_EXPORT" in result["blockers"]
    assert "PAPER_EXECUTION_SESSIONS" in result["blockers"]


def test_challenger_sessions_are_not_frozen_baseline_evidence():
    data = fixture()
    data["capital"]["prospective_completed_sessions"] = 10000
    result = evaluate(**data)
    assert result["prospective_challenger_sessions"] == 10000
    assert result["prospective_frozen_paper_sessions"] == 0
    assert "PRE_REGISTERED_INDEPENDENT_FORWARD" in result["blockers"]
    assert "PAPER_EXECUTION_SESSIONS" in result["blockers"]


def test_incomplete_qqq_matching_is_blocked():
    data = fixture()
    data["report"]["no_contributions"]["qqq_buy_hold"]["paid_capital"] = 50000
    result = evaluate(**data)
    assert "MATCHED_QQQ_BENCHMARK" in result["blockers"]


def test_fooled_price_history_does_not_claim_integrity():
    data = fixture()
    data["report"]["observed_instruments"] = ["QQQ", "SYNTHETIC_3X"]
    result = evaluate(**data)
    assert "OBSERVED_ETF_HISTORY" in result["blockers"]


def test_many_paper_sessions_cannot_override_absent_trade_fills():
    data = fixture()
    data["paper_gap"].update({"status": "PASS", "paper_sessions": 300,
                              "paired_sessions": 300,
                              "component_attribution": {"status": "IDENTIFIED"}})
    data["benchmark"].update({"status": "PASS", "sessions": 300,
                              "stocklens_return": 0.3, "qqq_return": 0.2})
    result = evaluate(**data)
    assert result["status"] == "BLOCKED_FOR_LIVE_TRADING"
    assert "LIVE_EXECUTION_TIME_PARITY" in result["blockers"]
    assert "BROKER_SANDBOX_DRY_RUN" in result["blockers"]
    assert result["automated_live_trading_authorized"] is False


def test_decision_parity_required_even_when_backtest_is_valid():
    data = fixture()
    audit = evaluate(**data)
    assert "SHARED_FROZEN_DECISION_PARITY" in audit["blockers"]
    data["decision_parity"] = {
        "status": "PASS",
        "equal_frozen_target": True,
        "signal_asof": "2026-10-07",
        "research_asof": "2026-10-07",
        "broker_orders_authorized": False,
        "errors": [],
    }
    checked = evaluate(**data)
    assert "SHARED_FROZEN_DECISION_PARITY" not in checked["blockers"]
    assert checked["status"] == "BLOCKED_FOR_LIVE_TRADING"
    assert checked["automated_live_trading_authorized"] is False

from copy import deepcopy

from frozen_decision_parity_gate import compare


def pair():
    decision = {
        "asof_date": "2026-10-07", "level": 3, "defense_active": False,
        "target_leverage": 3.0, "qqq_weight": 0.0, "tqqq_weight": 0.985,
        "invested_fraction": 0.985, "qqq_adjusted_close": 757.72998046875,
        "decision_source": "stocklens.core.replay_levels",
    }
    report = {
        "status": "PASS", "observed_instruments": ["QQQ", "TQQQ"],
        "period": {"end": "2026-10-07"},
        "latest_frozen_decision": decision
    }
    signal = {
        "mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
        "state_replay": "EXACT_FROM_2009_09_01_WITH_PRESTART_WARMUP",
        "latest": {**decision, "features": {"close": decision["qqq_adjusted_close"]}},
        "data_audit": {"last_close": decision["qqq_adjusted_close"]},
        "execution_plan": {"broker_actions_enabled": False},
    }
    return report, signal


def test_equal_target_passes_without_claiming_execution_parity():
    report, signal = pair()
    result = compare(report, signal)
    assert result["status"] == "PASS"
    assert result["intraday_execution_parity_proven"] is False
    assert result["broker_orders_authorized"] is False


def test_one_different_level_blocks():
    report, signal = pair()
    signal["latest"]["level"] = 2
    assert "LEVEL_MISMATCH" in compare(report, signal)["errors"]


def test_one_different_exposure_blocks():
    report, signal = pair()
    signal["latest"]["target_leverage"] = 1.25
    assert "TARGET_LEVERAGE_MISMATCH" in compare(report, signal)["errors"]


def test_adjusted_qqq_close_drift_blocks():
    report, signal = pair()
    signal["data_audit"]["last_close"] *= 1.01
    assert "QQQ_ADJUSTED_CLOSE_DRIFT" in compare(report, signal)["errors"]


def test_future_signal_date_blocks():
    report, signal = pair()
    signal["latest"]["asof_date"] = "2026-10-08"
    assert "SIGNAL_DATE_MISMATCH" in compare(report, signal)["errors"]


def test_broker_actions_not_authorized():
    report, signal = pair()
    signal["execution_plan"]["broker_actions_enabled"] = True
    assert "LIVE_BROKER_ACTIONS_NOT_DISABLED" in compare(report, signal)["errors"]


def test_synthetic_price_report_rejected():
    report, signal = pair()
    report["observed_instruments"] = ["QQQ", "SYNTHETIC_QQQ_3X"]
    assert "NOT_OBSERVED_ETF_BACKTEST" in compare(report, signal)["errors"]


def test_state_machine_warmup_contract_enforced():
    report, signal = pair()
    signal["state_replay"] = "REPLAY_FROM_LAST_365_SESSIONS"
    assert "STATE_REPLAY_CONTRACT_CHANGED" in compare(report, signal)["errors"]

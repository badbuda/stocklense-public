import json
from pathlib import Path

import pytest

from observed_tqqq_only_gate import check


def _paths(tmp_path):
    policy = {
        "policy_id": "OBSERVED_TQQQ_ONLY_FOR_NEW_RESEARCH",
        "active": True,
        "never_fallback_to_synthetic": True,
        "earliest_eligible_date": "2010-02-09",
    }
    report = {
        "kind": "OBSERVED_QQQ_TQQQ_DAILY_OPEN_EXECUTION_PROXY",
        "observed_instruments": ["QQQ", "TQQQ"],
        "price_source": "YFINANCE_AUTO_ADJUSTED_DAILY_OPEN_AND_CLOSE",
        "price_fingerprint_sha256": "a" * 64,
        "first_valid_real_TQQQ_date": "2010-02-09",
        "period": {"start": "2010-02-09", "end": "2026-10-07", "sessions": 4000},
        "execution_policy": "Next-session adjusted daily OPEN proxy",
        "full_lean_execution_parity": False,
        "broker_fills_observed": False,
        "automatic_model_promotion": False,
        "automatic_trading_authorized": False,
        "no_contributions": {
            "start": "2010-02-09", "end": "2026-10-07",
            "stocklens": {"paid_capital": 100000},
            "qqq_buy_hold": {"paid_capital": 100000},
        },
        "initial_100k_monthly_3500": {
            "start": "2010-02-09", "end": "2026-10-07",
            "stocklens": {"paid_capital": 790000},
            "qqq_buy_hold": {"paid_capital": 790000},
        },
    }
    p = tmp_path / "policy.json"
    a = tmp_path / "current.json"
    b = tmp_path / "public.json"
    p.write_text(json.dumps(policy))
    a.write_text(json.dumps(report))
    b.write_text(json.dumps(report))
    return p, a, b, report


def test_observed_tqqq_is_authorized_without_model_promotion(tmp_path):
    p, a, b, _ = _paths(tmp_path)
    status = check(p, a, b)
    assert status["status"] == "PASS"
    assert status["synthetic_as_active_performance_evidence"] is False


@pytest.mark.parametrize("field,value", [
    ("kind", "SYNTHETIC_QQQ_TIMES_THREE"),
    ("price_source", "QQQ_RETURN_TIMES_EXPOSURE"),
    ("observed_instruments", ["QQQ"]),
    ("first_valid_real_TQQQ_date", "2010-03-01"),
    ("broker_fills_observed", True),
    ("automatic_model_promotion", True),
])
def test_gate_rejects_nonobserved_or_unsafe_sources(tmp_path, field, value):
    p, a, b, report = _paths(tmp_path)
    report[field] = value
    a.write_text(json.dumps(report))
    b.write_text(json.dumps(report))
    with pytest.raises(RuntimeError, match="OBSERVED_TQQQ_ONLY_POLICY_FAILED"):
        check(p, a, b)


def test_no_fabricated_preinception_returns(tmp_path):
    p, a, b, report = _paths(tmp_path)
    report["period"]["start"] = "2009-09-01"
    report["no_contributions"]["start"] = "2009-09-01"
    report["initial_100k_monthly_3500"]["start"] = "2009-09-01"
    a.write_text(json.dumps(report))
    b.write_text(json.dumps(report))
    with pytest.raises(RuntimeError, match="SYNTHETIC_PREINCEPTION_DATES"):
        check(p, a, b)


def test_mismatched_qqq_and_tqqq_capital_not_allowed(tmp_path):
    p, a, b, report = _paths(tmp_path)
    report["no_contributions"]["qqq_buy_hold"]["paid_capital"] = 90000
    a.write_text(json.dumps(report))
    b.write_text(json.dumps(report))
    with pytest.raises(RuntimeError, match="UNEQUAL_CONTRIBUTIONS"):
        check(p, a, b)


def test_nonidentical_public_report_rejected(tmp_path):
    p, a, b, report = _paths(tmp_path)
    b.write_text(json.dumps({"report": "stale"}))
    with pytest.raises(RuntimeError, match="PUBLIC_SOURCE_MISMATCH"):
        check(p, a, b)

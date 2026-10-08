import copy

import pytest

from observed_tqqq_risk_audit import evaluate


def _report():
    rows = [
        {"date": "2026-01-05", "stocklens_nav": 100000., "qqq_nav": 100000.},
        {"date": "2026-01-06", "stocklens_nav": 110000., "qqq_nav": 105000.},
        {"date": "2026-01-07", "stocklens_nav": 88000., "qqq_nav": 102000.},
    ]
    return {
        "observed_instruments": ["QQQ", "TQQQ"],
        "broker_fills_observed": False,
        "automatic_model_promotion": False,
        "price_fingerprint_sha256": "a" * 64,
        "period": {"start": rows[0]["date"], "end": rows[-1]["date"], "sessions": len(rows)},
        "no_contributions": {
            "start": rows[0]["date"], "end": rows[-1]["date"],
            "sessions": 3, "monthly_contribution": 0.0,
            "daily_nav_rows": rows,
            "stocklens": {"ending_equity": 88000., "max_drawdown": -0.2,
                          "cagr_without_contributions": -0.2},
            "qqq_buy_hold": {"ending_equity": 102000., "max_drawdown": -(3000. / 105000.),
                             "cagr_without_contributions": 0.02},
        },
    }


def test_risk_audit_uses_observed_instrument_path():
    result = evaluate(_report())
    assert result["status"] == "PASS"
    assert result["full_path"]["stocklens_max_drawdown"] == pytest.approx(-0.2)
    assert result["statistical_independence_proven"] is False
    assert result["automatic_model_promotion"] is False


@pytest.mark.parametrize("mutation,code", [
    (lambda x: x["no_contributions"].pop("daily_nav_rows"), "MISSING_FULL"),
    (lambda x: x["no_contributions"]["daily_nav_rows"][1].update({"date":"2026-01-05"}), "DUPLICATE"),
    (lambda x: x["no_contributions"]["daily_nav_rows"][2].update({"stocklens_nav":0}), "INVALID_NAV"),
    (lambda x: x["no_contributions"]["stocklens"].update({"ending_equity":87000.}), "ENDPOINT_NAV"),
    (lambda x: x["no_contributions"].update({"monthly_contribution":3500.}), "CONTRIBUTIONS"),
    (lambda x: x.update({"broker_fills_observed":True}), "UNVERIFIED"),
])
def test_risk_audit_fails_closed(mutation, code):
    report = copy.deepcopy(_report())
    mutation(report)
    with pytest.raises(ValueError, match=code):
        evaluate(report)

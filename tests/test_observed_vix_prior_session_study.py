"""Tiny toy VIX and ETF sessions test causal clocks; never claim toy alpha."""
import pytest
from observed_vix_prior_session_study import (
    normalize_csv, source_validation, target, simulate, OFFICIAL_VIX_URL,
)
from observed_etf_four_challengers_batch import simulate as frozen_sim


def small():
    dates = ["2024-03-18", "2024-03-19", "2024-03-20",
             "2024-03-21", "2024-03-22", "2024-03-25",
             "2024-03-26", "2024-03-27"]
    rows = [{"date": d,
             "signal": "2024-03-15" if not i else dates[i-1],
             "l": [3, 3, 3, 3, 3, 2, 1.25, 0][i],
             "qo": 100.+i, "qc": 100.5+i,
             "to": 20.+i*.15, "tc": 20.2+i*.15}
            for i, d in enumerate(dates)]
    v = [14., 20., 36., 40., 28., 26., 21., 14.]
    src = {"schema_version": 1, "series": "CBOE_VIX_INDEX_DAILY_CLOSE",
           "source_url": OFFICIAL_VIX_URL,
           "downloaded_historical_snapshot_first_seen_proven": False,
           "provider_publication_time_independently_verified": False,
           "bars": [{"date": d, "vix_close": v[i]} for i, d in enumerate(dates)]}
    return rows, src


def test_cboe_csv_parser_and_inference_constraints():
    sample = "DATE,OPEN,HIGH,LOW,CLOSE\n03/18/2024,14,16,13,15\n03/19/2024,20,22,19,21\n"
    result = normalize_csv(sample)
    assert result[0]["date"] == "2024-03-18"
    assert result[1]["vix_close"] == 21.


def test_duplicate_or_missing_vix_rejected_not_forward_filled():
    rows, src = small()
    src["bars"].pop(3)
    with pytest.raises(ValueError, match="VIX_MISSING_PRIOR_COMPLETED_SESSION"):
        simulate(rows, src, mode="vix_high_tier")
    sample = "DATE,CLOSE\n03/18/2024,14\n03/18/2024,16\n"
    with pytest.raises(ValueError, match="VIX_DUPLICATE_EXCHANGE_DATE"):
        normalize_csv(sample)


def test_prior_session_vix_vs_same_day_release():
    rows, src = small()
    baseline = simulate(rows, src, mode="vix_high_tier")
    assert baseline["levels"][3] == 2.0  # prior 2024-03-20 VIX=36, not today's 40
    assert baseline["levels"][4] == 1.25  # previous date 2024-03-21 VIX=40
    mutation = small()[1]
    mutation["bars"][3]["vix_close"] = 120.
    after = simulate(rows, mutation, mode="vix_high_tier")
    assert baseline["navs"][:4] == after["navs"][:4]  # no future sensitivity


def test_fixed_shock_uses_five_older_completed_dates():
    assert target(3, "vix_five_session_shock", 30., 22.) == 2.
    assert target(3, "vix_five_session_shock", 24., 10.) == 3.
    assert target(0, "vix_high_tier", 50., 5.) == 0
    assert target(1.25, "vix_high_tier", 44., None) == 1.25


def test_baseline_exact_replay_parity_on_toy_real_style_prices():
    rows, src = small()
    for lag in (0, 1):
        for slip in (10., 20.):
            a = simulate(rows, src, "frozen", lag, slip)["navs"]
            b = frozen_sim(rows, mode="frozen", lag=lag, slippage_bps=slip)["navs"]
            assert a == pytest.approx(b, abs=1e-8)


def test_false_timestamp_attestation_not_accepted():
    rows, src = small()
    src["provider_publication_time_independently_verified"] = True
    with pytest.raises(ValueError, match="VIX_SOURCE_PROVENANCE_CONTRACT_INVALID"):
        source_validation(src, [r["date"] for r in rows])


def test_no_parameter_mining_or_uncapped_output():
    rows, src = small()
    with pytest.raises(ValueError, match="VIX_MODE_OR_COST_NOT_PREREGISTERED"):
        simulate(rows, src, "optimized_after_outcomes")
    for vix in (12., 29., 32., 41.):
        assert target(3, "vix_high_tier", vix, None) <= 3.

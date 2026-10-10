"""Adversarial tests of chart rounding stability: synthetic rows are NOT LEAN."""
import pytest

from qc_native_chart_precision_audit import evaluate, EPS


def record(day,close=110.,sma50=100.,sma200=99.,vol20=.20,mom12=.1,level=3,defense=False,leverage=3.):
    return dict(date=day,close=close,sma50=sma50,sma200=sma200,
                vol20=vol20,mom12=mom12,level=str(level),
                defense="true" if defense else "false",
                leverage=str(leverage))


def test_stable_decision_margins_are_conditional_not_source_attestation():
    rows=[record("2024-02-01"),record("2024-02-02",vol20=.24)]
    x=evaluate(rows)
    assert x["status"]=="BOUND_STABLE_ON_CHARTED_VALUES"
    assert x["conditionally_robust_if_true_plot_error_within_assumed_bounds"] is True
    assert x["observed_state_mathematical_matches"]==2
    assert x["immutable_original_session_state_verified"] is False
    assert x["original_unrounded_LEAN_indicator_bits_attested"] is False
    assert x["actual_plot_encoder_error_bound_independently_verified"] is False
    assert x["capital_deployment_authorized"] is False


def test_vol_near_unverified_plot_error_envelope_is_not_claimed_stable():
    rows=[record("2024-02-01",vol20=.28000005,level=2,leverage=2.)]
    x=evaluate(rows)
    assert x["status"]=="BOUND_COULD_FLIP_DECISION"
    assert x["fragile_sessions_first20"][0]["condition"]=="volatility_threshold"
    assert x["conditionally_robust_if_true_plot_error_within_assumed_bounds"] is False


def test_near_trend_cross_or_momentum_zero_is_not_proven_stable():
    # Close sits 0.00002 over SMA200*1.01 for the first decision (risk-off).
    r=record("2024-02-01",close=100. * 1.01 + .00002,sma200=100.,
             sma50=101.,level=3)
    x=evaluate([r])
    assert x["status"]=="BOUND_COULD_FLIP_DECISION"
    assert any(z["condition"]=="trend" for z in x["fragile_sessions_first20"])
    # sma50==sma200 has a non-strict derivative under any plot rounding.
    r=record("2024-02-02",sma50=99.,sma200=99.,mom12=1e-8)
    x=evaluate([r])
    assert any(z["condition"]=="sma50_sma200" for z in x["fragile_sessions_first20"])
    assert any(z["condition"]=="momentum_zero" for z in x["fragile_sessions_first20"])


def test_real_state_mismatch_cannot_be_mislabeled_as_precision_stable():
    a=record("2024-02-01",level=1,leverage=1.25)
    r=evaluate([a])
    assert r["status"]=="CHARTED_VALUE_COMPUTATION_MISMATCH"
    assert r["observed_state_mathematical_matches"]==0
    assert r["conditionally_robust_if_true_plot_error_within_assumed_bounds"] is False


@pytest.mark.parametrize("values",[
    {"close":0},{"sma200":-10},{"vol20":float("nan")},
])
def test_invalid_observations_rejected(values):
    a=record("2024-02-01")
    a.update(values)
    with pytest.raises(ValueError,match="INVALID_CHARTED_FEATURE"):
        evaluate([a])


def test_duplicate_dates_fail_closed():
    a=record("2024-02-01")
    with pytest.raises(ValueError,match="UNSORTED_DUPLICATE_FEATURE_DATES"):
        evaluate([a,a])


def test_nonpositive_or_omitted_assumed_error_rejected():
    with pytest.raises(ValueError,match="INVALID_ASSUMED_PLOT_ERROR_ENVELOPE"):
        evaluate([record("2024-02-01")],assumed_abs_error={**EPS,"mom12":0})
    with pytest.raises(ValueError,match="INVALID_ASSUMED_PLOT_ERROR_ENVELOPE"):
        evaluate([record("2024-02-01")],assumed_abs_error={"close":1e-5})


def test_private_native_csv_cannot_be_claimed_valid_when_missing(tmp_path):
    from qc_native_chart_precision_audit import audit
    with pytest.raises(ValueError,match="PINNED_ORIGINAL_LEAN_INPUT_VALIDATION_FAILED"):
        audit(tmp_path/"nonexistent.csv",out=tmp_path/"audit.json")

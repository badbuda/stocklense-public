"""Pure offline adversarial tests for day-by-day LEAN/Yahoo diagnostics."""
from __future__ import annotations

import pytest

from qc_lean_yahoo_daily_exposure_audit import diagnose


def samples():
    lean=[{"date": d, "leverage": l} for d,l in (
        ("2020-04-01",3.), ("2020-04-02",2.),
        ("2020-04-03",2.), ("2020-04-06",0.))]
    proxy=[{"date": d, "l": l, "signal": prev} for d,l,prev in (
        ("2020-04-01",3.,"2020-03-31"), ("2020-04-02",3.,"2020-04-01"),
        ("2020-04-03",2.,"2020-04-02"), ("2020-04-06",2.,"2020-04-03"))]
    return lean,proxy


def test_diagonal_and_lag_results_are_distinct_and_nonpromoting():
    original,proxy=samples()
    report=diagnose(original,proxy)
    assert report["overlap_sessions"]==4
    assert report["matching_exposure_sessions"]==2
    assert report["same_date_exposure_match_rate"]==0.5
    assert report["best_diagnostic_offset_in_yahoo_sessions"]==1
    assert next(x for x in report["lag_profile"]
                if x["offset_in_yahoo_exchange_sessions"]==1)["match_rate"]==1.0
    assert report["same_input_parity_proven"] is False
    assert report["diagnostic_lag_not_model_adjustment"] is True
    assert sum(x["sessions"] for x in report["confusion"])==4
    assert report["top_mismatch_episodes"][0]["sessions"]==1


def test_mismatches_and_missing_days_cannot_inflate_coverage():
    original,proxy=samples()
    proxy.pop(1)
    r=diagnose(original,proxy)
    assert r["overlap_sessions"]==3
    assert r["original_sessions_outside_proxy"]==1
    assert r["proxy_sessions_outside_original"]==0
    assert r["same_input_parity_proven"] is False


@pytest.mark.parametrize("mutation,expected",[
    (lambda p: p.append(dict(p[-1])), "DUPLICATE_OR_UNSORTED_PROXY_SESSIONS"),
    (lambda p: p[0].update(l=4.), "INVALID_PROXY_EXPOSURE"),
    (lambda p: p[0].update(l=float("nan")), "INVALID_PROXY_EXPOSURE"),
    (lambda p: p[0].update(signal=p[0]["date"]), "PROXY_SIGNAL_NOT_PRIOR_TO_EXECUTION"),
])
def test_invalid_proxy_fails_closed(mutation,expected):
    original,proxy=samples()
    mutation(proxy)
    with pytest.raises(ValueError,match=expected):
        diagnose(original,proxy)


def test_original_reference_cannot_be_duplicated_or_unsorted():
    original,proxy=samples()
    original.append(dict(original[0]))
    with pytest.raises(ValueError,match="INVALID_ORIGINAL_CHRONOLOGY_OR_LEVERAGE"):
        diagnose(original,proxy)
    original,proxy=samples()
    original=list(reversed(original))
    with pytest.raises(ValueError,match="UNSORTED_ORIGINAL_SESSIONS"):
        diagnose(original,proxy)


def test_exposure_regimes_do_not_hide_minority_level_error():
    reference,proxy=samples()
    result=diagnose(reference,proxy)
    counts=result["balanced_exposure_diagnostic"]
    assert counts["3x_reference_days"]==1
    assert counts["3x_matching_days"]==1
    assert counts["non_3x_reference_days"]==3
    assert counts["non_3x_matching_days"]==1
    assert counts["non_3x_match_rate"] == 1/3
    assert result["same_date_exposure_match_rate"]==0.5
    assert result["same_input_parity_proven"] is False


def test_initial_proxy_level_is_not_counted_as_transition():
    original,proxy=samples()
    result=diagnose(original,proxy)
    transitions=result["transitions"]
    # Synthetic setup: original changes at Apr 2 and Apr 6,
    # proxy changes at Apr 3, initial Apr 1 must never count as a trade.
    assert transitions["reference_events_inside_proxy_period"]==2
    assert transitions["proxy_events_excluding_initial_baseline"]==1
    assert transitions["exact_date_and_level_matches"]==0
    assert transitions["reference_events_not_in_proxy"] == [
        ["2020-04-02",2.0],["2020-04-06",0.0]]
    assert transitions["proxy_events_not_in_reference"] == [["2020-04-03",2.0]]


def test_pre_inception_is_not_mislabeled_as_missing_yahoo_data():
    original,proxy=samples()
    original.insert(0,{"date":"2020-03-31","leverage":3.0})
    result=diagnose(original,proxy)
    assert result["reference_before_yahoo_proxy_inception"] == 1
    assert result["missing_reference_sessions_inside_yahoo_proxy_window"] == 0


def test_published_cross_provider_audit_has_bounded_claims():
    import json
    from pathlib import Path
    report=json.loads(Path("research/lean_yahoo_cross_provider_20261009.json").read_text())
    assert report["overlap_sessions"] == 3662
    assert report["matching_exposures"] == 3655
    assert report["different_exposures"] == 7
    assert len(report["mismatch_days"]) == 7
    assert report["daily_exposure_match_rate"] == 3655/3662
    assert sum(a["compared"] for a in report["per_year"].values()) == 3662
    assert sum(a["matched"] for a in report["per_year"].values()) == 3655
    assert report["by_original_regime"]["non_3x"]["matching_days"] == 732
    assert report["exact_transition_date_and_level_pairs"]["exact_matches"] == 62
    assert report["lags_in_yahoo_trading_sessions"][2]["rate"] > report["lags_in_yahoo_trading_sessions"][3]["rate"]
    assert report["claims"]["same_input_feature_parity_proven"] is False
    assert report["claims"]["native_LEAN_source_code_identity_proven"] is False
    assert report["claims"]["alpha_vs_QQQ_or_TQQQ_proven"] is False
    assert report["claims"]["live_trading_authorized"] is False
    assert report["provenance"]["original_daily_date_leverage_sha256"] == "caa10bea0a07f3c5f6f60fef49fa407844da4ce514fa552e5202d6d1d10cefb5"

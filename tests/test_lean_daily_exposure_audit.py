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

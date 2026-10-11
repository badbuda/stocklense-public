"""Toy inputs test the as-of clock and modeled ledger, not historical cash alpha."""
import pytest

from research_cash_rate_broker_proxy import asof_open_rates, normalize, simulate
from observed_etf_four_challengers_batch import simulate as frozen_sim


def prices():
    return [
        {"date": "2024-03-18", "qo": 100.0, "qc": 101.0,
         "to": 20.0, "tc": 20.5, "l": 0, "signal": "2024-03-15"},
        {"date": "2024-03-19", "qo": 101.0, "qc": 101.5,
         "to": 20.5, "tc": 20.6, "l": 3, "signal": "2024-03-18"},
        {"date": "2024-03-20", "qo": 101.5, "qc": 101.3,
         "to": 20.6, "tc": 20.2, "l": 3, "signal": "2024-03-19"},
    ]


def data():
    return {"schema_version": 1, "series": "EFFR", "observations": [
        {"effective_date": "2024-03-15", "claimed_published_at_utc": "2024-03-18T13:00:00Z", "rate_percent": 5.3},
        {"effective_date": "2024-03-18", "claimed_published_at_utc": "2024-03-19T13:00:00Z", "rate_percent": 5.31},
    ]}


def test_asof_uses_prior_close_never_today_publication():
    assert asof_open_rates(prices(), data()) == pytest.approx([0.0, .053, .0531])


def test_outcome_mutation_after_last_prior_close_has_no_effect():
    a = data()
    x = asof_open_rates(prices(), a)
    a["observations"].append(
        {"effective_date": "2024-03-20", "claimed_published_at_utc": "2024-03-21T13:00:00Z", "rate_percent": 24})
    assert asof_open_rates(prices(), a) == x


def test_late_published_observation_not_available_at_open():
    a = data()
    a["observations"] = a["observations"][:1]\n    a["observations"][0]["claimed_published_at_utc"] = "2024-03-19T16:00:00Z"
    with pytest.raises(ValueError, match="RATE_NO_ASOF_QUOTE"):
        asof_open_rates(prices(), a)


def test_unit_percent_and_naive_datetime_fail_closed():
    a = data()
    a["observations"][0]["rate_percent"] = 530
    with pytest.raises(ValueError, match="RATE_OUTSIDE_PERCENT"):
        normalize(a)
    a = data()
    a["observations"][0]["claimed_published_at_utc"] = "2024-03-18T13:00:00"
    with pytest.raises(ValueError, match="RATE_ROW_REQUIRED_FIELDS"):
        normalize(a)


def test_non_overnight_discount_basis_not_cash_yield():
    a = data()
    a["series"] = "DTB3"
    with pytest.raises(ValueError, match="RATE_SERIES_NOT_OVERNIGHT"):
        normalize(a)


def test_zero_rate_exactly_matches_frozen_whole_share_ledger():
    rows = prices()
    actual = simulate(rows, [0., 0., 0.])
    frozen = frozen_sim(rows)["navs"]
    assert all(abs(a-b) < 1e-8 for a, b in zip(actual["navs"], frozen))
    assert actual["cash_interest_dollars"] == 0.
    assert actual["broker_interest_entitlement_proven"] is False


def test_positive_rates_pay_only_on_modeled_positive_cash():
    rows = prices()
    x = simulate(rows, [0., .05, .05])
    y = simulate(rows, [0., 0., 0.])
    assert x["cash_interest_dollars"] > 0
    assert x["stats"]["ending_equity"] > y["stats"]["ending_equity"]
    assert x["rate_clock_independently_verified"] is False


def test_invalid_rate_vector_and_backward_dates_fail():
    with pytest.raises(ValueError, match="RATE_DAILY_ALIGNMENT"):
        simulate(prices(), [0.])
    a = prices()
    a[1]["date"] = "2024-03-15"
    with pytest.raises(ValueError, match="RATE_INVALID_EXCHANGE_ORDER"):
        simulate(a, [0., .02, .02])

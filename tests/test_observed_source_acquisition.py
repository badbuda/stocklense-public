"""Network-independent adverse source intake tests. Toy prices are not alpha."""
from datetime import date
import pandas as pd
import pytest

from observed_source_acquisition import normalize_prices, normalize_effr_payload


def prices():
    x = pd.DataFrame({"Open": [1., 2., 3.], "Close": [2., 3., 4.]},
                     index=pd.to_datetime(["2024-03-18", "2024-03-19", "2024-03-20"]))
    return x


def test_observed_only_full_coverage_and_exact_dates():
    result = normalize_prices(prices(), "GLD",
                              ["2024-03-18", "2024-03-19", "2024-03-20"])
    assert len(result) == 3
    assert result[1] == {"date": "2024-03-19", "open": 2., "close": 3.}


def test_missing_day_never_forward_filled():
    with pytest.raises(ValueError, match="EXTERNAL_MISSING_REAL_OBSERVED_SESSIONS"):
        normalize_prices(prices().drop(pd.Timestamp("2024-03-19")), "TLT",
                         ["2024-03-18", "2024-03-19", "2024-03-20"])


def test_wrong_symbol_duplicate_and_invalid_price():
    with pytest.raises(ValueError, match="EXTERNAL_UNAPPROVED_SYMBOL"):
        normalize_prices(prices(), "QQQ", ["2024-03-18"])
    with pytest.raises(ValueError, match="EXTERNAL_DUPLICATE"):
        normalize_prices(pd.concat([prices(), prices().iloc[:1]]), "GLD",
                         ["2024-03-18"])
    x = prices()
    x.loc[pd.Timestamp("2024-03-19"), "Open"] = float("nan")
    with pytest.raises(ValueError, match="EXTERNAL_INVALID_OBSERVED_BAR"):
        normalize_prices(x, "GLD", ["2024-03-18", "2024-03-19"])


def test_yahoo_style_multiindex_columns():
    x = prices()
    x.columns = pd.MultiIndex.from_product([["Open", "Close"], ["TLT"]])
    assert normalize_prices(x, "TLT", ["2024-03-18"])[0]["close"] == 2.


def test_effr_only_effective_date_not_vendor_first_seen():
    p = {"refRates": [{"effectiveDate": "2024-03-18", "percentRate": 5.33},
                      {"effectiveDate": "2024-03-19", "percentRate": "5.32"}]}
    rows = normalize_effr_payload(p, "2024-03-18", "2024-03-19")
    assert len(rows) == 2
    assert rows[1]["rate_percent"] == 5.32
    assert rows[0]["provider_publication_timestamp_verified"] is False
    assert "published_at" not in rows[0]


def test_effr_missing_malformed_and_revised_conflict_fail_closed():
    with pytest.raises(ValueError, match="EFFR_API_SCHEMA"):
        normalize_effr_payload({"message": "not rates"}, "2024-03-18", "2024-03-19")
    with pytest.raises(ValueError, match="EFFR_MULTIPLE_VINTAGES"):
        normalize_effr_payload({"refRates": [
            {"effectiveDate": "2024-03-18", "percentRate": 5.30},
            {"effectiveDate": "2024-03-18", "percentRate": 5.31},
        ]}, "2024-03-18", "2024-03-19")


def test_effr_bad_units_and_empty_cohort_rejected():
    with pytest.raises(ValueError, match="EFFR_INVALID_PERCENT"):
        normalize_effr_payload({"refRates": [
            {"effectiveDate": "2024-03-18", "percentRate": 530},
        ]}, "2024-03-18", "2024-03-19")
    with pytest.raises(ValueError, match="EFFR_NO_MATCHING_EFFECTIVE_DATES"):
        normalize_effr_payload({"refRates": [
            {"effectiveDate": "2024-03-01", "percentRate": 5.3},
        ]}, "2024-03-18", "2024-03-19")

"""Only data contracts, never model-generated GLD/TLT investment results."""
import pytest

from research_diversified_sleeve_contract import inspect


def market():
    return [{"date": d} for d in ("2024-03-18", "2024-03-19", "2024-03-20")]


def candidate():
    return {"schema_version": 1, "price_basis": "OBSERVED_ADJUSTED_DAILY_OPEN_CLOSE",
            "source_urls": {"GLD": "https://example.org/gld", "TLT": "https://example.org/tlt"},
            "bars": {
                "GLD": [{"date": d["date"], "open": 200., "close": 201.} for d in market()],
                "TLT": [{"date": d["date"], "open": 90., "close": 91.} for d in market()],
            }}


def test_contract_only_never_claims_performance_or_audited_source():
    x = inspect(market(), candidate())
    assert x["matched_observed_sessions"] == 3
    assert x["source_first_seen_independently_proven"] is False
    assert x["price_alpha_proven"] is False
    assert x["live_trade_eligible"] is False
    assert "cagr" not in x


def test_missing_asset_cannot_masquerade_as_diversified_portfolio():
    a = candidate()
    a["bars"].pop("TLT")
    with pytest.raises(ValueError, match="SLEEVE_MISSING_REQUIRED_NONNASDAQ"):
        inspect(market(), a)


def test_missing_day_and_misalignment_both_fail_closed():
    a = candidate()
    a["bars"]["GLD"].pop()
    with pytest.raises(ValueError, match="SLEEVE_MISSING_FULL_REAL_ETF_COVERAGE"):
        inspect(market(), a)
    a = candidate()
    a["bars"]["TLT"][1]["date"] = "2024-03-18"
    with pytest.raises(ValueError, match="SLEEVE_ETF_DATES_NOT_ALIGNED"):
        inspect(market(), a)


def test_fake_price_nan_negative_and_self_attestation_do_not_help():
    a = candidate()
    a["bars"]["GLD"][0]["open"] = float("nan")
    a["source_independently_audited"] = True
    with pytest.raises(ValueError, match="SLEEVE_INVALID_PRICE"):
        inspect(market(), a)
    a = candidate()
    a["source_independently_audited"] = True
    assert inspect(market(), a)["source_first_seen_independently_proven"] is False


def test_non_https_metadata_and_unadjusted_prices_not_admitted():
    a = candidate()
    a["source_urls"]["TLT"] = "http://example.com/tlt"
    with pytest.raises(ValueError, match="SLEEVE_UNTRUSTED_SOURCE_URL"):
        inspect(market(), a)
    a = candidate()
    a["price_basis"] = "RAW_DAILY_PRICES"
    with pytest.raises(ValueError, match="SLEEVE_NOT_OBSERVED_ADJUSTED_BARS"):
        inspect(market(), a)

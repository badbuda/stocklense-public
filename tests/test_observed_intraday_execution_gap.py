import pytest
from observed_intraday_execution_gap import evaluate


def _prices():
    return {
        "QQQ": {
            "2026-10-06": {"09:30": 100, "09:31": 99, "09:32": 101},
            "2026-10-07": {"09:30": 102, "09:31": 102, "09:32": 102.5},
        },
        "TQQQ": {
            "2026-10-06": {"09:30": 20, "09:31": 18, "09:32": 22},
            "2026-10-07": {"09:30": 19, "09:31": 19, "09:32": 19.5},
        },
    }


def test_minute_gap_uses_observed_tqqq_not_three_times_qqq():
    report = evaluate(_prices(), asof_ny="2026-10-08")
    assert report["sessions"] == 2
    assert report["status"] == "OBSERVED_SAMPLE_NOT_FILL_PARITY"
    sample = report["samples"][0]
    assert sample["TQQQ"]["sell_0931_minus_0930_bps"] == pytest.approx(-1000)
    assert sample["QQQ"]["sell_0931_minus_0930_bps"] == pytest.approx(-100)
    assert sample["TQQQ"]["buy_0932_minus_0930_bps"] == pytest.approx(1000)
    assert report["broker_fill_parity"] is False
    assert report["automatic_trading_authorized"] is False


def test_absent_real_tqqq_quote_is_excluded_never_filled():
    rows = _prices()
    rows["TQQQ"]["2026-10-07"].pop("09:32")
    report = evaluate(rows, asof_ny="2026-10-08")
    assert report["sessions"] == 1
    assert any(x["reason"] == "MISSING_OBSERVED_MINUTE:TQQQ" for x in report["excluded"])


def test_current_and_future_sessions_are_not_validated():
    report = evaluate(_prices(), asof_ny="2026-10-07")
    assert report["sessions"] == 1
    assert any(x["date"] == "2026-10-07" and "UNVERIFIED" in x["reason"]
               for x in report["excluded"])


def test_empty_or_unmatched_markets_fail_closed():
    result = evaluate({"QQQ": {"2026-10-06": {}}, "TQQQ": {}},
                      asof_ny="2026-10-08")
    assert result["status"] == "NO_VERIFIED_OBSERVED_SAMPLE"
    assert result["sessions"] == 0
    assert result["statistics"]["TQQQ"]["sell_0931_minus_0930_bps"]["mean_bps"] is None

"""F-09: observed ETF minute-close completeness; normal and XNYS half sessions."""
import pandas as pd
import pytest

from stocklens.paper import _eod_close, PaperIntegrityError


def bars(day, count, close=80.0):
    index=pd.date_range(day+" 09:30", periods=count, freq="min",
                        tz="America/New_York")
    return pd.DataFrame({"Open":[close]*count,"Close":[close]*count},index=index)


def test_regular_session_complete_eod_close_passes():
    assert _eod_close(bars("2026-10-09", 390, 81.28), "2026-10-09", "TQQQ")==81.28


def test_vendor_truncated_session_cannot_use_last_available_price_as_close():
    with pytest.raises(PaperIntegrityError, match="TOO_FEW_MINUTE_BARS"):
        _eod_close(bars("2026-10-09", 100), "2026-10-09", "TQQQ")


def test_close_timestamp_must_reach_final_minutes():
    x=bars("2026-10-09",390)
    # Missing final 3 one-minute bars despite nearly complete session.
    with pytest.raises(PaperIntegrityError, match="MISSING_NEAR_SESSION_CLOSE"):
        _eod_close(x.iloc[:-3], "2026-10-09", "TQQQ")


def test_half_day_uses_actual_xnys_early_close_not_1600():
    # NYSE closes 13:00 ET on the Friday after Thanksgiving.
    assert _eod_close(bars("2026-11-27",210,89.),"2026-11-27","TQQQ")==89.


def test_half_day_truncation_is_rejected():
    with pytest.raises(PaperIntegrityError, match="TOO_FEW_MINUTE_BARS"):
        _eod_close(bars("2026-11-27",100),"2026-11-27","TQQQ")


def test_weekend_fake_prices_are_never_a_completed_paper_session():
    with pytest.raises(PaperIntegrityError, match="NON_XNYS_PAPER_SESSION"):
        _eod_close(bars("2026-10-10",390),"2026-10-10","TQQQ")


def test_duplicate_minute_prices_cannot_inflate_completeness():
    x=bars("2026-10-09",390)
    with pytest.raises(PaperIntegrityError, match="DUPLICATE_MINUTE_BARS"):
        _eod_close(pd.concat([x, x.iloc[:1]]),"2026-10-09","TQQQ")

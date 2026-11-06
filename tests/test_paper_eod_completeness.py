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


def test_partial_yahoo_minute_response_retries_before_accepting(monkeypatch):
    from datetime import date
    from types import SimpleNamespace
    import sys
    import stocklens.paper as paper

    seen = []
    def download(symbol, **kwargs):
        seen.append((symbol, kwargs))
        return bars("2026-11-05", 289 if len(seen) == 1 else 390, 81.25)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    monkeypatch.setattr(paper._time, "sleep", lambda _: None)
    observed = paper._fetch_intraday(
        "QQQ", date(2026, 11, 5), date(2026, 11, 6),
        expected_session="2026-11-05",
    )
    assert len(seen) == 2
    assert len(observed) == 390
    assert paper._eod_close(observed, "2026-11-05", "QQQ") == 81.25


def test_permanently_partial_yahoo_minute_response_fails_closed(monkeypatch):
    from datetime import date
    from types import SimpleNamespace
    import sys
    import stocklens.paper as paper

    calls = []
    def download(symbol, **kwargs):
        calls.append(symbol)
        return bars("2026-11-05", 289)
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    monkeypatch.setattr(paper._time, "sleep", lambda _: None)
    with pytest.raises(PaperIntegrityError, match=r"INTRADAY_FETCH_FAILED:QQQ:TOO_FEW_MINUTE_BARS:QQQ:2026-11-05:289:required=385"):
        paper._fetch_intraday(
            "QQQ", date(2026, 11, 5), date(2026, 11, 6),
            expected_session="2026-11-05",
        )
    assert calls == ["QQQ", "QQQ", "QQQ"]


def test_missing_market_close_not_accepted_by_retries(monkeypatch):
    from datetime import date
    from types import SimpleNamespace
    import sys
    import stocklens.paper as paper

    attempts = []
    full = bars("2026-11-05", 390)
    def download(symbol, **kwargs):
        attempts.append(symbol)
        return full.iloc[:389].drop(index=full.index[-2])
    monkeypatch.setitem(sys.modules, "yfinance", SimpleNamespace(download=download))
    monkeypatch.setattr(paper._time, "sleep", lambda _: None)
    with pytest.raises(PaperIntegrityError, match="INTRADAY_FETCH_FAILED:QQQ:MISSING_NEAR_SESSION_CLOSE"):
        paper._fetch_intraday(
            "QQQ", date(2026, 11, 5), date(2026, 11, 6),
            expected_session="2026-11-05",
        )
    assert len(attempts) == 3

from observed_etf_market_calendar_audit import audit


def _row(day, q=100., t=50.):
    return {
        "date": day,
        "qqq_adjusted_open": str(q),
        "qqq_adjusted_close": str(q),
        "tqqq_adjusted_open": str(t),
        "tqqq_adjusted_close": str(t),
    }


def test_complete_observed_exchange_cohort_passes():
    rows = [_row("2026-10-05"), _row("2026-10-06"), _row("2026-10-07")]
    result = audit(rows, ["2026-10-05", "2026-10-06", "2026-10-07"])
    assert result["status"] == "PASS"
    assert not result["missing_sessions"]
    assert result["independent_vendor_price_validation"] is False
    assert result["broker_fills_verified"] is False


def test_both_etfs_missing_one_exchange_session_is_visible():
    rows = [_row("2026-10-05"), _row("2026-10-07")]
    result = audit(rows, ["2026-10-05", "2026-10-06", "2026-10-07"])
    assert result["status"] == "FAIL"
    assert result["missing_sessions"] == ["2026-10-06"]


def test_weekend_or_duplicate_are_not_accepted():
    rows = [_row("2026-10-05"), _row("2026-10-05"), _row("2026-10-10")]
    result = audit(rows, ["2026-10-05"])
    assert result["status"] == "FAIL"
    assert result["bad_rows"]
    assert "2026-10-10" in result["unexpected_sessions"]


def test_nonfinite_and_zero_prices_fail_closed():
    rows = [_row("2026-10-05"), _row("2026-10-06", t=0)]
    result = audit(rows, ["2026-10-05", "2026-10-06"])
    assert result["status"] == "FAIL"
    assert result["bad_rows"]


def test_large_price_move_is_review_flag_not_hidden():
    rows = [_row("2026-10-05", t=50), _row("2026-10-06", t=90)]
    result = audit(rows, ["2026-10-05", "2026-10-06"])
    assert result["status"] == "PASS"
    assert len(result["large_daily_move_review_flags"]) == 1
    assert result["large_daily_move_review_flags"][0]["symbol"] == "TQQQ"

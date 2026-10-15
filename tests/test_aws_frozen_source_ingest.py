"""Offline canonical frozen-source ingest contract tests.

The old frozen loader remains unchanged. These tests inject a DataFrame
rather than contacting Yahoo, AWS, GitHub or any brokerage.
"""
from datetime import datetime, timezone
import csv
import io

import pandas as pd
import pytest

from infra.aws.independent_frozen_ingest import (
    ingest_frozen_yfinance, PROVIDER
)
from stocklens.data import _feature_window_sha256
from infra.aws.independent_signal_producer import build_signal
from test_aws_independent_pipeline import daily_fixture


def old_loader_fixture():
    payload, day, clock = daily_fixture()
    import io
    from infra.aws.independent_market_ingest import extract_adjusted_qqq
    raw, _ = extract_adjusted_qqq(payload, now=clock, expected_session=day)
    df = pd.read_csv(io.BytesIO(raw))
    df["Date"] = pd.to_datetime(df["Date"])
    reference_fp = _feature_window_sha256(df, 253)
    audit = {
        "source": "YFINANCE_QQQ_AUTO_ADJUSTED",
        "raw_rows": len(df),
        "completed_rows": len(df),
        "raw_last_date": day,
        "last_completed_date": day,
        "dropped_incomplete_current_session": False,
        "feature_window_sha256": reference_fp,
    }
    return df, audit, day, clock


def test_frozen_old_source_roundtrip_preserves_every_numeric_float():
    df, audit, day, clock = old_loader_fixture()
    called = []
    def loader(*, now_ny):
        called.append(now_ny)
        return df, audit
    raw, receipt = ingest_frozen_yfinance(day, now=clock, loader=loader)
    assert called and called[0].tzinfo is not None
    assert receipt["provider"] == PROVIDER
    assert receipt["last_session"] == day
    assert receipt["reference_feature_window_sha256"] == audit["feature_window_sha256"]
    assert receipt["independent_quote_vendor_parity_proven"] is False
    assert receipt["vendor_raw_http_bytes_archived"] is False
    assert receipt["source_path"] == "stocklens.data.load_qqq_history"
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    assert len(rows) == len(df)
    for expected, row in zip(df["Close"], rows):
        # Python float decoding must roundtrip even if a pandas fast parser
        # would round at a different stage.
        assert float(expected) == float(row["Close"])
    report = build_signal(raw, clock, source=PROVIDER,
                          source_sha256=receipt["csv_sha256"])
    assert report["latest"]["asof_date"] == day
    assert report["data_audit"]["feature_window_sha256"] == audit["feature_window_sha256"]


def test_prior_to_ny_1800_refuses_to_fetch_or_write():
    df, audit, day, clock = old_loader_fixture()
    def forbidden(*, now_ny):
        raise AssertionError("must not retrieve incomplete current NY session")
    with pytest.raises(ValueError, match="SESSION_INCOMPLETE"):
        ingest_frozen_yfinance(day, now=clock.replace(hour=17), loader=forbidden)


def test_nontrading_holiday_is_rejected_before_provider_call():
    def forbidden(*, now_ny):
        raise AssertionError("NYSE holiday must not fetch")
    with pytest.raises(ValueError, match="NOT_XNYS_SESSION"):
        ingest_frozen_yfinance("2026-12-25",
                              now=datetime(2026, 12, 25, 23, 30, tzinfo=timezone.utc),
                              loader=forbidden)


def test_wrong_or_unverified_source_label_rejected():
    df, audit, day, clock = old_loader_fixture()
    modified = dict(audit, source="CSV:pretend")
    with pytest.raises(ValueError, match="FROZEN_SOURCE_REQUIRED"):
        ingest_frozen_yfinance(day, now=clock,
                              loader=lambda *, now_ny: (df, modified))


def test_recent_price_change_with_stale_old_fingerprint_fails():
    df, audit, day, clock = old_loader_fixture()
    tampered = df.copy()
    tampered.loc[len(df)-1, "Close"] *= 0.99
    with pytest.raises(ValueError, match="FROZEN_FINGERPRINT_MISMATCH"):
        ingest_frozen_yfinance(day, now=clock,
                              loader=lambda *, now_ny: (tampered, audit))


def test_past_session_must_match_exact_last_trading_date():
    df, audit, day, clock = old_loader_fixture()
    stale = df.iloc[:-1].copy()
    stale_audit = dict(audit, completed_rows=len(stale),
                       last_completed_date=stale.iloc[-1]["Date"].date().isoformat())
    with pytest.raises(ValueError, match="STALE_OR_SHORT_HISTORY"):
        ingest_frozen_yfinance(day, now=clock,
                              loader=lambda *, now_ny: (stale, stale_audit))


def test_new_source_has_no_partial_data_silently_added():
    df, audit, day, clock = old_loader_fixture()
    partial = df.copy()
    partial.loc[len(partial)] = [
        pd.Timestamp(day) + pd.Timedelta(days=1), float(df.iloc[-1]["Close"])
    ]
    bad_audit = dict(audit, completed_rows=len(partial),
                     last_completed_date=(pd.Timestamp(day)+pd.Timedelta(days=1)).date().isoformat())
    with pytest.raises(ValueError, match="STALE_OR_SHORT_HISTORY"):
        ingest_frozen_yfinance(day, now=clock,
                              loader=lambda *, now_ny: (partial, bad_audit))


def test_requires_real_old_source_completion_metadata():
    df, audit, day, clock = old_loader_fixture()
    broken = dict(audit, last_completed_date="2010-10-01")
    with pytest.raises(ValueError, match="AUDIT_LAST_SESSION_MISMATCH"):
        ingest_frozen_yfinance(day, now=clock,
                              loader=lambda *, now_ny: (df, broken))

"""Offline, falsifiable same-Yahoo two-source-data-path parity tests.

Never fetch the live market and never talk to AWS, GitHub or a broker.
"""
from datetime import datetime, timedelta, timezone
import math

import pandas as pd
import pytest

from infra.aws.source_parity import (
    _completed_chart, compare_completed_histories,
    completed_xnys_session, compare_live_paths,
)
from infra.aws.independent_market_ingest import extract_adjusted_qqq
from test_aws_independent_pipeline import daily_fixture


def history():
    payload, session, clock = daily_fixture()
    csv_bytes, audit = extract_adjusted_qqq(
        payload, now=clock, expected_session=session
    )
    data = pd.read_csv(__import__("io").BytesIO(csv_bytes))
    data["Date"] = pd.to_datetime(data["Date"])
    return payload, session, clock, csv_bytes, data


def test_identical_adjusted_prices_and_frozen_decisions_pass():
    _, session, clock, csv_bytes, df = history()
    report = compare_completed_histories(
        vendor_raw=csv_bytes, reference_df=df, expected_session=session, now=clock
    )
    assert report["status"] == "STAGING_SAME_VENDOR_PATH_PARITY_PASS"
    assert report["calendar_equal"]
    assert report["mismatch_count"] == 0
    assert report["feature_fingerprints_equal"]
    assert report["decisions_equal"]
    assert report["second_provider_proven"] is False
    assert report["market_data_written"] is False
    assert report["broker_actions"] is False


def test_divergent_historical_adjusted_close_rejected_even_if_features_unchanged():
    _, session, clock, csv_bytes, df = history()
    df.loc[15, "Close"] *= 1.01
    report = compare_completed_histories(
        vendor_raw=csv_bytes, reference_df=df, expected_session=session, now=clock
    )
    assert report["status"] == "STAGING_SAME_VENDOR_PATH_PARITY_MISMATCH"
    assert report["mismatch_count"] == 1
    # A changed pre-trading-start price may leave the frozen decisions
    # unchanged. Never misreport "decision mismatch" merely because of
    # numeric mismatch; price divergence still fails the overall gate.
    assert report["decision_check_executed"] is True
    assert report["outside_binary32_precision_count"] == 1
    assert report["numeric_rounding_compatible"] is False
    assert report["policy_mismatch_count"] >= 0


def test_missing_historical_session_cannot_be_silently_reindexed():
    _, session, clock, csv_bytes, df = history()
    df = df.drop(index=[87]).reset_index(drop=True)
    report = compare_completed_histories(
        vendor_raw=csv_bytes, reference_df=df, expected_session=session, now=clock
    )
    assert report["status"] == "STAGING_SAME_VENDOR_PATH_PARITY_MISMATCH"
    assert report["calendar_equal"] is False
    assert report["decisions_equal"] is False
    assert report["mismatch_count"] is None
    assert report["decision_check_executed"] is False




def test_three_binary32_ulps_can_be_price_compatible_without_waving_policy_changes():
    _, session, clock, csv_bytes, df = history()
    # The real reported 2008 example is ~3 binary32 ULPs. Inject exactly
    # that precision-scale deviation in old warmup history, not 1% noise.
    old = float(df.loc[15, "Close"])
    ulp = math.ldexp(1.0, math.frexp(old)[1] - 1 - 23)
    df.loc[15, "Close"] = old + 3 * ulp
    report = compare_completed_histories(
        vendor_raw=csv_bytes, reference_df=df,
        expected_session=session, now=clock,
    )
    assert report["status"] == "STAGING_SAME_VENDOR_PATH_PARITY_PASS"
    assert report["price_precision_classification"] == "WITHIN_8_BINARY32_ULPS"
    assert report["mismatch_count"] == 1
    assert report["outside_binary32_precision_count"] == 0
    assert report["max_binary32_ulp_distance"] <= 8
    assert report["numeric_rounding_compatible"] is True
    assert report["decision_check_executed"] is True
    assert report["policy_mismatch_count"] == 0
    assert report["decisions_equal"] is True
    assert report["second_provider_proven"] is False
    assert report["price_rounding_origin_proven"] is False


def test_nine_binary32_ulps_fail_even_when_trading_policy_identical():
    _, session, clock, csv_bytes, df = history()
    old = float(df.loc[15, "Close"])
    ulp = math.ldexp(1.0, math.frexp(old)[1] - 1 - 23)
    df.loc[15, "Close"] = old + 9 * ulp
    report = compare_completed_histories(
        vendor_raw=csv_bytes, reference_df=df,
        expected_session=session, now=clock,
    )
    assert report["status"] == "STAGING_SAME_VENDOR_PATH_PARITY_MISMATCH"
    assert report["outside_binary32_precision_count"] == 1
    assert report["numeric_rounding_compatible"] is False
    assert report["decision_check_executed"] is True
    # Numeric mismatch is real even when semantic decisions remain unchanged.
    assert report["decisions_equal"] is True


def test_historical_policy_flip_is_reported_even_with_equal_latest_fingerprint():
    _, session, clock, csv_bytes, df = history()
    # A large one-day historic dislocation in 2009/2010 should change the
    # frozen day's level/defense independently of the current feature window.
    # Row 450 is after Sep-2009 trading start yet strictly before the
    # final 253-session window (740 - 253 = 487).
    df.loc[450, "Close"] *= 0.15
    report = compare_completed_histories(
        vendor_raw=csv_bytes, reference_df=df,
        expected_session=session, now=clock,
    )
    assert report["status"] == "STAGING_SAME_VENDOR_PATH_PARITY_MISMATCH"
    assert report["feature_fingerprints_equal"] is True
    assert report["decision_check_executed"] is True
    assert report["policy_mismatch_count"] > 0
    assert report["first_policy_mismatches"]
    assert report["decisions_equal"] is False


def test_recent_binary32_difference_not_accepted_if_fingerprint_changes():
    _, session, clock, csv_bytes, df = history()
    old = float(df.loc[len(df)-1, "Close"])
    ulp = math.ldexp(1.0, math.frexp(old)[1] - 1 - 23)
    df.loc[len(df)-1, "Close"] = old + ulp
    report = compare_completed_histories(
        vendor_raw=csv_bytes, reference_df=df,
        expected_session=session, now=clock,
    )
    assert report["numeric_rounding_compatible"] is True
    assert report["feature_fingerprints_equal"] is False
    assert report["status"] == "STAGING_SAME_VENDOR_PATH_PARITY_MISMATCH"

def test_stale_yfinance_reference_session_fails_closed():
    _, session, clock, csv_bytes, df = history()
    with pytest.raises(ValueError, match="SOURCE_PARITY_INCOMPLETE_OR_STALE"):
        compare_completed_histories(
            vendor_raw=csv_bytes, reference_df=df.iloc[:-1],
            expected_session=session, now=clock
        )


def test_open_current_bar_dropped_for_probe_only():
    payload, session, clock, csv_bytes, df = history()
    now = clock.replace(hour=15)
    trimmed, dropped, raw_last = _completed_chart(payload, now=now)
    assert dropped is True
    assert raw_last == session
    assert len(trimmed["chart"]["result"][0]["timestamp"]) == len(df) - 1
    assert len(payload["chart"]["result"][0]["timestamp"]) == len(df)
    # A real production signal may NEVER use this drop-to-history workaround.
    with pytest.raises(Exception):
        extract_adjusted_qqq(payload, now=now, expected_session=session)


def test_nyse_calendar_handles_open_day_and_completed_day():
    assert completed_xnys_session(
        datetime(2026, 10, 12, 20, 30, tzinfo=timezone.utc)
    ) == "2026-10-09"
    assert completed_xnys_session(
        datetime(2026, 10, 13, 0, 30, tzinfo=timezone.utc)
    ) == "2026-10-12"
    assert completed_xnys_session(
        datetime(2026, 12, 25, 23, 0, tzinfo=timezone.utc)
    ) == "2026-12-24"


def test_probe_is_readonly_injected_sources():
    payload, session, clock, csv_bytes, df = history()
    result = compare_live_paths(
        now=clock,
        chart_fetch=lambda *, now: (payload, "f"*64),
        reference_fetch=lambda *, now: (df, {"dropped_incomplete_current_session": False}),
    )
    assert result["status"] == "STAGING_SAME_VENDOR_PATH_PARITY_PASS"
    assert result["last_date"] == session
    assert result["vendor_raw_response_sha256"] == "f"*64
    assert result["dropped_incomplete_vendor_current_session"] is False
    assert result["market_data_written"] is False


def test_parity_acceptance_script_has_no_broker_or_s3_write():
    from pathlib import Path
    import subprocess
    p = Path("infra/aws/accept_independent_staging.sh")
    subprocess.run(["bash", "-n", str(p)], check=True)
    text = p.read_text()
    assert "STAGING_SAME_VENDOR_PATH_PARITY" in text
    assert "SAME_YAHOO_TWO_PATH_PARITY_PASS" in text
    assert "SAME_VENDOR_PRICE_PARITY_FAILED" in text
    assert "second_provider_proven" in text
    assert "aws events enable-rule" not in text
    assert "aws s3api put-object" not in text
    assert "aws cloudformation delete-stack" not in text


def test_zip_includes_frozen_yfinance_source_path_and_comparator():
    from pathlib import Path
    src = Path("infra/aws/deploy_independent_staging.sh").read_text()
    assert '"stocklens/data.py"' in src
    assert '"infra/aws/source_parity.py"' in src

"""Pure offline tests: never call Yahoo, AWS, GitHub, or a broker."""
from __future__ import annotations
import csv
import io
import hashlib
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest
from infra.aws.independent_market_ingest import (
    MarketDataError, extract_adjusted_qqq
)
from infra.aws.independent_pipeline import run


NY = ZoneInfo("America/New_York")


def freeze_source_fixture(raw, audit):
    """Only tests the canonical contract; pure vendor extractor remains separate."""
    rows = list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    window = "\n".join(
        f"{r['Date']},{float(r['Close']):.12g}" for r in rows[-253:]
    )
    return {
        **audit,
        "provider": "YFINANCE_QQQ_AUTO_ADJUSTED",
        "source_path": "stocklens.data.load_qqq_history",
        "data_integrity_status": "FROZEN_YFINANCE_SOURCE_VERIFIED_NOT_INDEPENDENT_VENDOR",
        "reference_feature_window_sha256": hashlib.sha256(window.encode()).hexdigest(),
    }


def daily_fixture(count=740):
    days = []
    d = date(2008, 1, 2)
    while len(days) < count:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    timestamps = [
        int(datetime.combine(day, time(16, 0), NY).timestamp())
        for day in days
    ]
    prices = [100.0 + 0.01 * index for index in range(len(days))]
    payload = {"chart": {"error": None, "result": [{
        "meta": {"symbol": "QQQ", "exchangeTimezoneName": "America/New_York"},
        "timestamp": timestamps,
        "indicators": {"adjclose": [{"adjclose": prices}]},
    }]}}
    clock = datetime.combine(days[-1], time(19, 0), NY)
    return payload, days[-1].isoformat(), clock


def test_extract_completed_vendor_adjusted_history():
    payload, day, clock = daily_fixture()
    raw, audit = extract_adjusted_qqq(payload, now=clock, expected_session=day)
    rows = list(csv.DictReader(io.StringIO(raw.decode())))
    assert len(rows) == 740
    assert rows[-1]["Date"] == day
    assert audit["provider"] == "YAHOO_CHART_PUBLIC_ENDPOINT"
    assert audit["validation_scope"].endswith("NO_INDEPENDENT_VENDOR_PARITY")


def test_rejects_open_session():
    payload, day, clock = daily_fixture()
    clock = clock.replace(hour=17)
    with pytest.raises(MarketDataError, match="SESSION_NOT_COMPLETED"):
        extract_adjusted_qqq(payload, now=clock, expected_session=day)


def test_rejects_missing_adjusted_values():
    payload, day, clock = daily_fixture()
    payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"][-2] = None
    with pytest.raises(MarketDataError, match="MISSING_VENDOR_PRICE"):
        extract_adjusted_qqq(payload, now=clock, expected_session=day)


def test_rejects_stale_latest_bar():
    payload, day, clock = daily_fixture()
    payload["chart"]["result"][0]["timestamp"].pop()
    payload["chart"]["result"][0]["indicators"]["adjclose"][0]["adjclose"].pop()
    with pytest.raises(MarketDataError, match="LAST_VENDOR_SESSION_MISMATCH"):
        extract_adjusted_qqq(payload, now=clock, expected_session=day)


def test_rejects_wrong_symbol():
    payload, day, clock = daily_fixture()
    payload["chart"]["result"][0]["meta"]["symbol"] = "SPY"
    with pytest.raises(MarketDataError, match="WRONG_VENDOR_SYMBOL"):
        extract_adjusted_qqq(payload, now=clock, expected_session=day)


def test_rejects_vendor_duplicate_day():
    payload, day, clock = daily_fixture()
    payload["chart"]["result"][0]["timestamp"][-1] = payload["chart"]["result"][0]["timestamp"][-2]
    with pytest.raises(MarketDataError, match="VENDOR_DATE_NOT_STRICTLY_INCREASING"):
        extract_adjusted_qqq(payload, now=clock, expected_session=day)


class MockPreconditionFailed(Exception):
    response = {"ResponseMetadata": {"HTTPStatusCode": 412}}


class InMemoryVersionedS3:
    def __init__(self):
        self.data = {}

    def put_object(self, **kw):
        key = kw["Key"]
        if key in self.data:
            raise MockPreconditionFailed("already exists")
        self.data[key] = kw["Body"]
        return {"VersionId": "v1"}

    def get_object(self, **kw):
        return {"Body": io.BytesIO(self.data[kw["Key"]]), "VersionId": "v1"}


def test_staged_pipeline_end_to_end_and_idempotence():
    payload, day, clock = daily_fixture()
    raw, audit = extract_adjusted_qqq(payload, now=clock, expected_session=day)
    audit = freeze_source_fixture(raw, audit)
    audit["vendor_response_sha256"] = "fixture-response-hash"

    def fixture_ingest(session, *, now):
        assert session == day and now == clock
        return raw, audit

    s3 = InMemoryVersionedS3()
    receipt = run(expected_session=day, now=clock, s3=s3,
                  bucket="test", ingest_fn=fixture_ingest)
    assert receipt["status"] == "STAGED_SIGNAL_ARCHIVED"
    assert receipt["broker_actions"] is False
    assert receipt["vendor_parity_proven"] is False
    assert receipt["canonical_source"] == "YFINANCE_QQQ_AUTO_ADJUSTED"
    assert receipt["frozen_feature_window_sha256"] == audit["reference_feature_window_sha256"]
    assert len(s3.data) == 3
    repeat = run(expected_session=day, now=clock, s3=s3,
                 bucket="test", ingest_fn=fixture_ingest)
    assert receipt == repeat


def test_detects_divergent_immutable_vendor_revision():
    payload, day, clock = daily_fixture()
    raw, audit = extract_adjusted_qqq(payload, now=clock, expected_session=day)
    audit = freeze_source_fixture(raw, audit)
    s3 = InMemoryVersionedS3()

    def ingest_a(session, *, now):
        return raw, audit

    run(expected_session=day, now=clock, s3=s3, bucket="test", ingest_fn=ingest_a)
    altered = raw.replace(b"100", b"101", 1)
    from hashlib import sha256
    changed_audit = dict(audit, csv_sha256=sha256(altered).hexdigest())

    def ingest_b(session, *, now):
        return altered, changed_audit

    with pytest.raises(RuntimeError, match="DIVERGENT_IMMUTABLE_MARKET_REVISION"):
        run(expected_session=day, now=clock, s3=s3, bucket="test", ingest_fn=ingest_b)


def test_retry_after_new_retrieval_timestamp_preserves_original_signal_receipt():
    from datetime import timedelta
    payload, day, clock = daily_fixture()
    raw, audit = extract_adjusted_qqq(payload, now=clock, expected_session=day)
    audit = freeze_source_fixture(raw, audit)
    s3 = InMemoryVersionedS3()
    def first(session, *, now):
        return raw, audit
    original = run(expected_session=day, now=clock, s3=s3,
                   bucket="test", ingest_fn=first)
    def later(session, *, now):
        fresh_audit = dict(audit, retrieved_at_utc=now.isoformat())
        return raw, fresh_audit
    retry = run(expected_session=day, now=clock + timedelta(minutes=25),
                s3=s3, bucket="test", ingest_fn=later)
    assert retry == original
    assert len(s3.data) == 3



def test_chart_provider_is_rejected_before_any_staging_s3_mutation():
    payload, day, clock = daily_fixture()
    raw, audit = extract_adjusted_qqq(payload, now=clock, expected_session=day)
    s3 = InMemoryVersionedS3()
    with pytest.raises(RuntimeError, match="FROZEN_YFINANCE_SOURCE_REQUIRED"):
        run(expected_session=day, now=clock, s3=s3, bucket="test",
            ingest_fn=lambda session, *, now: (raw, audit))
    assert s3.data == {}


def test_frozen_source_fingerprint_mismatch_fails_without_s3_writes():
    payload, day, clock = daily_fixture()
    raw, audit = extract_adjusted_qqq(payload, now=clock, expected_session=day)
    audit = freeze_source_fixture(raw, audit)
    audit["reference_feature_window_sha256"] = "0"*64
    s3 = InMemoryVersionedS3()
    with pytest.raises(RuntimeError, match="FROZEN_SOURCE_FEATURE_FINGERPRINT_MISMATCH"):
        run(expected_session=day, now=clock, s3=s3, bucket="test",
            ingest_fn=lambda session, *, now: (raw, audit))
    # All source/feature checks must occur before the first S3 mutation.
    assert s3.data == {}

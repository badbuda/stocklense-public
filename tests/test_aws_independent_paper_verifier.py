"""Offline independent AWS Paper receipt-chain verification tests."""
import pytest

from infra.aws.verify_independent_paper import verify
from test_aws_independent_paper import (
    FakeS3, THURS, FRI, MON, NOW_FRI, NOW_MON,
    observed_market, seed_signal,
)
from infra.aws.independent_paper import run_paper


def completed_chain():
    s3 = FakeS3()
    for day, data in (("2026-10-08", THURS), ("2026-10-09", FRI),
                      ("2026-10-12", MON)):
        seed_signal(s3, day, data)
    market = lambda prior, session: observed_market(session)
    run_paper(session="2026-10-09", now=NOW_FRI, s3=s3,
              bucket="test", bootstrap=True, market_fetch=market)
    run_paper(session="2026-10-12", now=NOW_MON, s3=s3,
              bucket="test", market_fetch=market)
    return s3


def test_full_accounting_receipt_chain_verifies():
    s3 = completed_chain()
    report = verify(session="2026-10-12", s3=s3, bucket="test")
    assert report["status"] == "AWS_ONLY_PAPER_RECEIPT_VERIFIED"
    assert report["audited_sessions"] == 2
    assert report["broker_fills_observed"] is False
    assert report["vendor_raw_http_receipt_archived"] is False


def test_market_receipt_corruption_fails_verification():
    s3 = completed_chain()
    key = "market/paper/2026-10-12.json"
    s3.data[key] = s3.data[key].replace(b"YFINANCE_1M_RAW", b"CORRUPTED_MARKET")
    with pytest.raises(Exception):
        verify(session="2026-10-12", s3=s3, bucket="test")


def test_previous_paper_receipt_mutation_breaks_chain():
    s3 = completed_chain()
    key = "paper/sessions/2026-10-09.json"
    s3.data[key] += b" "
    with pytest.raises(RuntimeError, match="PAPER_PREVIOUS_SHA_CHAIN_MISMATCH"):
        verify(session="2026-10-12", s3=s3, bucket="test")

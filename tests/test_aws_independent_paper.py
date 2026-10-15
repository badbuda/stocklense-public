"""Offline prospective AWS-only Paper 8.0 tests, no real network/AWS."""
from __future__ import annotations

from datetime import datetime, timezone
import io
import json

import pytest
from infra.aws.independent_paper import build_paper_receipt, run_paper
from stocklens.paper import SessionMarket


def signal(day, stamp):
    return {
        "version": "8.0.2-shadow-completed-session-guard",
        "mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
        "signal_source": "QQQ_ADJUSTED_DAILY_CLOSE",
        "generated_at_utc": stamp,
        "latest": {
            "asof_date": day,
            "level": 3,
            "defense_active": False,
            "target_leverage": 3.0,
            "qqq_weight": 0.0,
            "tqqq_weight": 0.985,
        },
        "action": "NO_CHANGE",
        "execution_plan": {"broker_actions_enabled": False},
    }


THURS = signal("2026-10-08", "2026-10-08T23:00:00+00:00")
FRI = signal("2026-10-09", "2026-10-09T23:00:00+00:00")
MON = signal("2026-10-12", "2026-10-12T23:00:00+00:00")
NOW_FRI = datetime(2026, 10, 9, 23, 30, tzinfo=timezone.utc)
NOW_MON = datetime(2026, 10, 12, 23, 30, tzinfo=timezone.utc)


def observed_market(day):
    return SessionMarket(
        session_date=day,
        prices_0931={"QQQ": 100.0, "TQQQ": 80.0},
        prices_0932={"QQQ": 101.0, "TQQQ": 81.0},
        closes={"QQQ": 102.0, "TQQQ": 82.0},
        dividends={"QQQ": 0.0, "TQQQ": 0.0},
        split_ratios={"QQQ": 0.0, "TQQQ": 0.0},
        source="YFINANCE_1M_RAW",
    )


def test_explicit_prospective_bootstrap_and_full_ledger_integrity():
    with pytest.raises(ValueError, match="EXPLICIT_PROSPECTIVE_BOOTSTRAP_REQUIRED"):
        build_paper_receipt(
            session="2026-10-09", current_signal=FRI, prior_signal=THURS,
            market=observed_market("2026-10-09"), now=NOW_FRI,
            previous_receipt=None
        )
    receipt = build_paper_receipt(
        session="2026-10-09", current_signal=FRI, prior_signal=THURS,
        market=observed_market("2026-10-09"), now=NOW_FRI,
        previous_receipt=None, bootstrap=True
    )
    assert receipt["integrity"]["status"] == "PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS"
    assert receipt["row"]["trade_count_session"] >= 1
    assert receipt["state"]["last_mark_session"] == "2026-10-09"
    assert receipt["broker_fills_observed"] is False
    assert receipt["broker_orders_authorized"] is False
    assert receipt["bootstrap_start"] == "2026-10-09"


def test_rejects_late_prior_signal_and_missing_session():
    late = signal("2026-10-08", "2026-10-09T14:00:00+00:00")
    with pytest.raises(ValueError, match="PRIOR_SIGNAL_CREATED_AFTER_MARKET_OPEN"):
        build_paper_receipt(
            session="2026-10-09", current_signal=FRI, prior_signal=late,
            market=observed_market("2026-10-09"), now=NOW_FRI,
            previous_receipt=None, bootstrap=True
        )
    with pytest.raises(ValueError, match="UNEXPECTED_OBSERVED_EXECUTION_SOURCE"):
        bad = observed_market("2026-10-09")
        bad = SessionMarket(**{**bad.__dict__, "source": "SYNTHETIC"})
        build_paper_receipt(
            session="2026-10-09", current_signal=FRI, prior_signal=THURS,
            market=bad, now=NOW_FRI, previous_receipt=None, bootstrap=True
        )


class Missing(Exception):
    response = {"Error": {"Code": "NoSuchKey"}}


class Precondition(Exception):
    response = {"ResponseMetadata": {"HTTPStatusCode": 412}}


class FakeS3:
    def __init__(self):
        self.data = {}

    def get_object(self, **kwargs):
        if kwargs["Key"] not in self.data:
            raise Missing()
        return {
            "Body": io.BytesIO(self.data[kwargs["Key"]]),
            "VersionId": "version-id",
            # S3 server time is now mandatory for continuity classification.
            "LastModified": datetime(2026, 10, 13, 0, 0, tzinfo=timezone.utc),
        }

    def put_object(self, **kwargs):
        if kwargs["Key"] in self.data:
            raise Precondition()
        self.data[kwargs["Key"]] = kwargs["Body"]
        return {"VersionId": "version-id"}


def seed_signal(s3, day, value):
    s3.data[f"signals/{day}.json"] = json.dumps(value).encode()


def test_two_session_aws_paper_chain_preserves_accounting_and_fails_closed():
    s3 = FakeS3()
    for d, obj in (("2026-10-08", THURS), ("2026-10-09", FRI),
                   ("2026-10-12", MON)):
        seed_signal(s3, d, obj)

    fetch = lambda prior, session: observed_market(session)
    with pytest.raises(RuntimeError, match="MISSING_PREVIOUS_CONTINUITY_RECORD|MISSING_PAPER_PREVIOUS_SESSION"):
        run_paper(session="2026-10-09", now=NOW_FRI, s3=s3,
                  bucket="fixture", market_fetch=fetch)

    first = run_paper(session="2026-10-09", now=NOW_FRI, s3=s3,
                      bucket="fixture", bootstrap=True, market_fetch=fetch)
    assert first["status"] == "STAGED_PAPER_VERIFIED"
    assert first["broker_orders"] is False
    assert len(s3.data) == 7  # 3 signals, genesis, market, receipt, continuity

    same = run_paper(session="2026-10-09", now=NOW_FRI, s3=s3,
                     bucket="fixture", bootstrap=True, market_fetch=fetch)
    assert first == same

    # Now refused earlier by the durable book-genesis guard (stronger, same intent).
    with pytest.raises(RuntimeError, match="REBOOTSTRAP_NOT_ALLOWED_BOOK_EXISTS|PAPER_PREVIOUS_SESSION_EXISTS"):
        run_paper(session="2026-10-12", now=NOW_MON, s3=s3,
                  bucket="fixture", bootstrap=True, market_fetch=fetch)

    second = run_paper(session="2026-10-12", now=NOW_MON, s3=s3,
                       bucket="fixture", market_fetch=fetch)
    assert second["status"] == "STAGED_PAPER_VERIFIED"
    receipt = json.loads(s3.data["paper/sessions/2026-10-12.json"])
    assert receipt["integrity"]["verified_paper_sessions"] == 2
    assert len(receipt["history"]["ledger"]) == 2
    assert receipt["prior_receipt_sha256"]
    assert receipt["row"]["session_date"] == "2026-10-12"
    assert receipt["broker_fills_observed"] is False
    assert second["broker_fills"] is False

"""Adversarial follow-up for PR #78 v2. Intentionally FAILS until v2 issues are fixed.

Requires Claude's v2 patch and its tests/test_aws_session_continuity.py fixture.
No AWS credentials/network/trading.
"""
from datetime import datetime, timezone
import hashlib
import pytest

from infra.aws import session_continuity as sc
from infra.aws.independent_session_watchdog import inspect

U=lambda *args: datetime(*args, tzinfo=timezone.utc)


def pair():
    a=sc.build_record(session="2026-10-09",status=sc.ON_TIME,
                      previous_record=None,previous_record_sha256=None,
                      processed_at=U(2026,10,9,23),signal_archived_at=U(2026,10,8,23),
                      book=sc.BOOK,evidence={"paper_sha256":"a"*64})
    b=sc.build_record(session="2026-10-12",status=sc.ON_TIME,
                      previous_record=a,previous_record_sha256=hashlib.sha256(sc.canonical(a)).hexdigest(),
                      processed_at=U(2026,10,12,23),signal_archived_at=U(2026,10,9,23),
                      book=sc.BOOK,evidence={"paper_sha256":"b"*64})
    return a,b


@pytest.mark.parametrize("field,new_value",[
    ("epoch",99),
    ("qualified_streak_in_epoch",252),
    ("totals",{sc.ON_TIME:252,sc.LATE:0,sc.RECONSTRUCTED:0,sc.MISSED:0}),
])
def test_validator_rejects_forged_maturity(field,new_value):
    a,b=pair()
    b[field]=new_value
    assert sc.validate_record(b,session=b["session"],previous=a,receipt_sha256="b"*64), (
        f"Forged {field} silently accepted; can falsely claim 63/252-session readiness")


def test_validator_rejects_forged_timing_without_cross_check():
    a,b=pair()
    b["processed_at_utc"]=U(2026,10,12,10).isoformat() # before XNYS open/close
    assert sc.validate_record(b,session=b["session"],previous=a,receipt_sha256="b"*64), (
        "ON_TIME is accepted although the record states it was processed before session close")


def test_validator_enforces_predecessor_session_even_for_matching_hash():
    a,b=pair()
    b["session"]="2026-10-13" # skips 2026-10-12; predecessor is Fri 2026-10-09
    assert sc.validate_record(b,session=b["session"],previous=a,receipt_sha256="b"*64), (
        "A hash match is insufficient without exchange-session adjacency")


def test_watchdog_rejects_252_streak_in_two_records():
    a,b=pair()
    b["qualified_streak_in_epoch"]=252
    records={a["session"]:a,b["session"]:b}
    receipts={a["session"]:"a"*64,b["session"]:"b"*64}
    result=inspect(now=U(2026,10,13,15),rule_state="ENABLED",
                   expected_rule_state="ENABLED",monitoring_start="2026-10-09",
                   read_record=lambda date:records.get(date),
                   read_receipt_sha=lambda date: receipts.get(date))
    assert result["status"]=="FAIL_CLOSED", "Watchdog ignored counterfeit qualified streak"


def test_missing_prev_continuity_does_not_write_orphan_paper():
    from infra.aws.independent_paper import run_paper
    from test_aws_session_continuity import _bootstrap,seed,fetch
    s3=_bootstrap()
    del s3.data["paper/continuity/2026-10-09.json"]
    seed(s3,"2026-10-12","2026-10-12T23:00:00+00:00",U(2026,10,12,23,1))
    s3.clock=U(2026,10,12,23,30)
    with pytest.raises(RuntimeError,match="CONTINUITY|CHAIN"):
        run_paper(session="2026-10-12",now=U(2026,10,12,23,30),
                  s3=s3,bucket="b",market_fetch=fetch)
    assert "paper/sessions/2026-10-12.json" not in s3.data, (
        "Orphan immutable Paper receipt was written BEFORE predecessor-chain guard")


def test_malformed_vendor_exception_cannot_be_silently_missed():
    from infra.aws.independent_paper import run_paper_catchup
    from test_aws_session_continuity import _bootstrap,seed
    s3=_bootstrap()
    seed(s3,"2026-10-12","2026-10-12T23:00:00+00:00",U(2026,10,12,23,1))
    s3.clock=U(2026,10,12,23,30)
    def coding_bug(prior, session):
        raise ValueError("MALFORMED_UPSTREAM_PROVIDER_SCHEMA")
    with pytest.raises(ValueError,match="MALFORMED_UPSTREAM_PROVIDER_SCHEMA"):
        run_paper_catchup(target_session="2026-10-12",now=U(2026,10,12,23,30),
                          s3=s3,bucket="b",market_fetch=coding_bug)
    assert "paper/continuity/2026-10-12.json" not in s3.data, (
        "Vendor schema/parser failures must not be reclassified as observed bars unavailable")

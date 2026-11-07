"""Read-only, epoch-scoped structure verifier for ST Paper Epoch 2.

This is NOT the live AWS Watchdog. The original 2026-11-05/06 incident
must remain FAIL_CLOSED independently of any new book. Even a completely
linked new book is only STRUCTURALLY_VERIFIED: actual model, market data,
accounting and provider freshness require separate independent acceptance.
No AWS clients, EventBridge, broker, alarms or writes.
"""
from __future__ import annotations

from typing import Callable

from stocklens import paper_epoch as epoch
from stocklens.epoch2_store import Epoch2Store, Receipt, GENESIS, GAPS, require


def inspect_epoch2(read: Callable[[str], Receipt | None], *,
                   expected_completed_sessions: list[str]) -> dict:
    """Check exact supplied expected sessions, not a calendar oracle.

    A future private watchdog MUST derive expected sessions independently
    from the exchange calendar and authenticated market completion evidence.
    """
    base = {
        "old_epoch":"FAIL_CLOSED_MISSING_2026_11_05_AND_06",
        "original_alarms_may_be_cleared":False,
        "new_epoch":"NOT_QUALIFIED",
        "cross_epoch_nav_allowed":False,
        "operational_watchdog_green":False,
        "independent_NAV_or_market_validation":False,
        "aws_mutations":False,
        "broker_orders":False,
    }
    require(isinstance(expected_completed_sessions,list) and
            len(expected_completed_sessions)>0 and
            expected_completed_sessions[0]==epoch.FIRST_NEW_DAY and
            len(expected_completed_sessions)==len(set(expected_completed_sessions)) and
            expected_completed_sessions==sorted(expected_completed_sessions),
            "INVALID_EXPECTED_SESSION_CALENDAR")
    g=read(GENESIS)
    if g is None:
        return {**base,"new_epoch":"MISSING_GENESIS_FAIL_CLOSED"}
    require(g.record.get("book")==epoch.NEW_BOOK and
            g.record.get("old_book_preserved") is True and
            g.record.get("broker_orders") is False and
            g.record.get("manifest_sha256")==epoch.sha(g.record.get("manifest",{})) and
            g.record.get("manifest",{}).get("original_book_anchors")==epoch.HISTORIC_SHA256,
            "INVALID_NEW_EPOCH_GENESIS")
    gap=read(GAPS)
    if gap is None:
        return {**base,"new_epoch":"MISSING_HISTORIC_GAP_AUDIT_FAIL_CLOSED"}
    require(gap.record.get("book")==epoch.NEW_BOOK and
            gap.record.get("status")=="MISSED_UNRECOVERABLE_NO_BACKFILL" and
            gap.record.get("old_receipt_keys_unchanged") is True and
            gap.record.get("missed_sessions")==list(epoch.MISSED) and
            gap.record.get("new_genesis_sha256")==g.sha256,
            "INVALID_HISTORIC_GAP_AUDIT")
    prev_paper_sha=g.sha256
    prev_cont_sha=g.sha256
    prev_day=epoch.PREVIOUS_SIGNAL_DAY
    complete=0
    for day in expected_completed_sessions:
        p=read(Epoch2Store.session_key(day))
        c=read(Epoch2Store.continuity_key(day))
        if p is None or c is None:
            return {**base,
                    "new_epoch":"SESSION_MISSING_OR_HALF_COMMITTED_FAIL_CLOSED",
                    "first_missing_session":day,
                    "structurally_verified_prior_sessions":complete}
        paper=p.record
        continuity=c.record
        require(paper.get("book")==epoch.NEW_BOOK and
                paper.get("session")==day and
                paper.get("prior_session")==prev_day and
                paper.get("previous_receipt_sha256")==prev_paper_sha and
                paper.get("genesis_sha256")==g.sha256 and
                paper.get("broker_orders_authorized") is False and
                paper.get("broker_fills_observed") is False and
                paper.get("paper_backfill") is False and
                paper.get("status")=="MODELED_FORWARD_SESSION_CANDIDATE" and
                isinstance(paper.get("state"),dict) and
                paper["state"].get("last_mark_session")==day,
                "PAPER_CANDIDATE_CHAIN_BROKEN")
        require(continuity.get("book")==epoch.NEW_BOOK and
                continuity.get("session")==day and
                continuity.get("status")=="ON_TIME_QUALIFIED" and
                continuity.get("paper_key")==p.key and
                continuity.get("paper_sha256")==p.sha256 and
                continuity.get("paper_version_id")==p.version and
                continuity.get("previous_record_sha256")==prev_cont_sha and
                continuity.get("genesis_sha256")==g.sha256 and
                continuity.get("broker_orders") is False and
                continuity.get("broker_fills") is False and
                continuity.get("old_epoch_alarm_preserved") is True,
                "CONTINUITY_SHA_OR_VERSION_CHAIN_BROKEN")
        prev_paper_sha=p.sha256
        prev_cont_sha=c.sha256
        prev_day=day
        complete+=1
    return {**base,
            "new_epoch":"STRUCTURALLY_LINKED_NOT_LIVE_ACCOUNTING_ACCEPTANCE",
            "structurally_verified_prior_sessions":complete,
            "last_structurally_verified_session":prev_day,
            "calendar_is_provided_not_independently_attested":True}

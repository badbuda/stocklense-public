#!/usr/bin/env python3
"""PROPOSAL ONLY: forward-only ST Paper epoch after an immutable chain break.

This is not a new Paper handler, not an alarm reset, and not a release script.
It verifies the deployed ST code/PROD isolation, frozen original old-epoch hash
anchors, complete old session/continuity hash links, exact missing Nov 5 and 6
receipts, and the preceding versioned Nov 6 signal (with no broker flag).

It returns a strictly DRAFT forward-only recovery contract with a NEW book ID
and independent NAV epoch, preserved original receipts/alarms, and strict gates.
No Lambda invoke, no S3/Dynamo writes, no CFN/Events/Alarm changes, no broker.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import sys

from infra.aws import st_paper_immutable_link_audit_readonly as immutable
from infra.aws import st_paper_weekend_direct_guarded_release as release

OLD_BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK"
OLD_LAST_SESSION = "2026-11-04"
MISSING = ("2026-11-05", "2026-11-06")
PROPOSED_FIRST_SESSION = "2026-11-09"
PROPOSED_BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH2_20261109"
SIGNAL_KEY = "signals/2026-11-06.json"
SOURCE_PINS = {
    f"paper/book/{OLD_BOOK}/genesis.json":
        "355398c0e93b9ea0aeb17f71fb90e4f040156314bff6eaf4fba3f3297c8cd8e1",
    "paper/sessions/2026-11-04.json":
        "797bccafa9aba7b3799c312bbd1ed2f67e0101c127f2bcbdec6318d91f2f22d2",
    "paper/continuity/2026-11-04.json":
        "92d39a078d1859b0f1870826b89eb093d610dcb279696b778ce4b8d709db6eae",
}


def require(ok, reason):
    if not ok:
        raise RuntimeError(reason)


def old_book_verified(records):
    require(records["genesis"]["book_matches"]=="MATCH" and
            records["genesis"]["initial_paper_link"]=="MATCH" and
            records["genesis"]["initial_continuity_link"]=="MATCH",
            "OLD_GENESIS_CHAIN_INTEGRITY_NOT_PROVEN")
    pairs=records.get("stored_hash_linkage", [])
    expected_pairs=[
        ("2026-10-30","2026-11-02"),
        ("2026-11-02","2026-11-03"),
        ("2026-11-03","2026-11-04"),
    ]
    require(len(pairs)==3, "OLD_PAPER_LINK_COUNT_UNEXPECTED")
    for pair, expected in zip(pairs,expected_pairs):
        require(pair.get("previous_session")==expected[0] and
                pair.get("session")==expected[1] and
                pair.get("paper_prior_receipt_link")=="MATCH" and
                pair.get("continuity_previous_record_link")=="MATCH",
                "OLD_PAPER_OR_CONTINUITY_LINK_BROKEN")
    require(records.get("missing_dates")==list(MISSING),
            "GAP_DATES_UNEXPECTED_NEED_REVIEW")
    for session in ("2026-10-30","2026-11-02","2026-11-03","2026-11-04"):
        pair=records.get("versioned_daily_records",{}).get(session,{})
        paper=pair.get("sessions",{})
        continuity=pair.get("continuity",{})
        require(paper.get("status")=="IMMUTABLE_VERSIONED_OBJECT_PRESENT" and
                paper.get("book_field")=="MATCH" and
                paper.get("session_field")=="MATCH" and
                paper.get("state_last_mark_session")=="MATCH" and
                paper.get("shadow_mode")=="MATCH" and
                paper.get("broker_fills_observed_false") is True and
                paper.get("broker_orders_authorized_false") is True,
                "UNQUALIFIED_OR_NONMODELED_ORIGINAL_PAPER:"+session)
        require(continuity.get("status")=="IMMUTABLE_VERSIONED_OBJECT_PRESENT" and
                continuity.get("continuity_status")=="ON_TIME_QUALIFIED" and
                continuity.get("qualified_in_record") is True and
                all(continuity.get(k)=="MATCH" for k in (
                    "book_field", "session_field", "paper_hash_attested",
                    "paper_key_attested", "paper_version_attested")) and
                continuity.get("broker_orders_false") is True and
                continuity.get("broker_fills_false") is True,
                "UNQUALIFIED_ORIGINAL_CONTINUITY:"+session)
    require(records.get("original_economic_accounting_status")==
            "NOT_ATTESTED_BY_HASH_LINKS",
            "UNEXPECTED_ACCOUNTING_ATTESTATION_LEVEL")
    return True


def prove_historic_anchors(s3):
    actual={}
    for key, expected in SOURCE_PINS.items():
        obj=immutable.stable_object(s3,key)
        require(obj is not None and obj.get("sha")==expected,
                "HISTORIC_ARCHIVE_PIN_CHANGED:"+key)
        actual[key]={"sha256":expected, "s3_version_id_verified":True}
    return actual


def next_market_session_proof():
    # No assumptions about weekends, market holidays or future half sessions.
    try:
        import exchange_calendars as xcals
    except ImportError:
        # A deliberately NARROW, externally reviewed date pin. NYSE's 2026
        # official calendar confirms 2026-11-09 is an ordinary exchange day;
        # 2026-11-06 is Friday, followed by the closed weekend. This fallback
        # NEVER authorizes a schedule or supports other calendar dates.
        from datetime import timedelta
        last = date.fromisoformat(MISSING[-1])
        first = date.fromisoformat(PROPOSED_FIRST_SESSION)
        require(last.isoformat()=="2026-11-06" and
                first.isoformat()=="2026-11-09" and
                last.weekday()==4 and first.weekday()==0 and
                (first-last)==timedelta(days=3),
                "PINNED_XNYS_NOV09_REFERENCE_DIFFERS")
        return {
            "status":"OFFICIAL_NYSE_2026_NOV09_NARROW_DATE_PIN_ONLY",
            "source":"https://www.nyse.com/trade/hours-calendars",
            "last_missing_session":last.isoformat(),
            "proposed_first_session":first.isoformat(),
            "general_xnys_calendar_unavailable":True,
            "new_epoch_scheduling_authorized":False,
        }
    cal=xcals.get_calendar("XNYS")
    last=date.fromisoformat(MISSING[-1])
    first=date.fromisoformat(PROPOSED_FIRST_SESSION)
    require(cal.is_session(last.isoformat()) and cal.is_session(first.isoformat()),
            "PROPOSED_FIRST_SESSION_NOT_EXCHANGE_DAY")
    next_day=cal.next_session(last.isoformat()).date()
    require(next_day==first, "PROPOSED_SESSION_NOT_NEXT_EXCHANGE_SESSION")
    return {"status":"XNYS_NEXT_SESSION_VERIFIED",
            "last_missing_session":last.isoformat(),
            "proposed_first_session":first.isoformat(),
            "new_epoch_scheduling_authorized":False}


def prior_signal_proof(s3):
    # Head and read exact S3 version; do not publish model inputs, exposures
    # or signal source content.
    obj=immutable.stable_object(s3,SIGNAL_KEY)
    require(obj is not None, "PRIOR_FROZEN_SIGNAL_MISSING")
    payload=obj["payload"]
    require(payload.get("mode")=="SHADOW_ONLY_NO_BROKER_ACTIONS",
            "PRIOR_SIGNAL_WRONG_MODE")
    plan=payload.get("execution_plan")
    require(isinstance(plan,dict) and
            plan.get("broker_actions_enabled") is False,
            "PRIOR_SIGNAL_MIGHT_ENABLE_BROKER")
    latest=payload.get("latest")
    require(isinstance(latest,dict) and latest.get("asof_date")==MISSING[-1],
            "PRIOR_SIGNAL_SESSION_INVALID")
    return {"status":"VERSIONED_FROZEN_NONBROKER_SIGNAL_READ",
            "session":MISSING[-1],"key":SIGNAL_KEY,
            "s3_version_verified":True,
            "source_sha256":obj["sha"],
            "timing_before_next_market_open":"NOT_ATTESTED_HERE",
            "market_data_completeness":"NOT_ATTESTED_HERE"}


def proposal(records, historic_pins, calendar, signal):
    old_book_verified(records)
    require(set(historic_pins)==set(SOURCE_PINS),
            "ORIGINAL_PINS_INCOMPLETE")
    require(signal.get("status")=="VERSIONED_FROZEN_NONBROKER_SIGNAL_READ",
            "PRIOR_FROZEN_SIGNAL_NOT_PROVEN")
    return {
        "status":"FORWARD_ONLY_EPOCH_RECOVERY_PROPOSAL_NOT_DEPLOYABLE",
        "old_epoch":{
            "book_id":OLD_BOOK,
            "last_qualified_session":OLD_LAST_SESSION,
            "genesis_and_links":"ALL_MATCH",
            "archived_immutable_anchor_sha256":SOURCE_PINS,
            "state":"BREACHED_AND_PRESERVED_UNCHANGED",
            "historical_alarm_truth":"PRESERVE_HISTORIC_FAIL_CLOSED",
            "historical_NAV_discontinuity":"EXPLICIT_NO_CROSS_EPOCH_PERFORMANCE",
        },
        "unqualified_sessions":[
            {"session":session,
             "proposed_gap_status":"MISSED_UNRECOVERABLE_NO_BACKFILL",
             "old_paper_receipt":"MISSING_AND_MUST_REMAIN_MISSING",
             "old_continuity":"MISSING_AND_MUST_REMAIN_MISSING",
             "broker_execution_claim":False}
            for session in MISSING
        ],
        "new_epoch":{
            "proposed_book_id":PROPOSED_BOOK,
            "proposed_first_exchange_session":PROPOSED_FIRST_SESSION,
            "calendar_check":calendar["status"],
            "initial_cash_holdings":"REQUIRES_EXPLICIT_NEW_INCEPTION_PROOF",
            "initial_NAV":"NO_VALUE_ASSIGNED_OR_INFERRED",
            "prior_signal_versioned":True,
            "prior_signal_causality":"NEEDS_TIMESTAMP_AND_LAG1_ATTESTATION",
            "execution_market_1m_completeness":"NEEDS_AT_LEAST_385_OF_390_SESSION_BARS",
            "ledger": "DISTINCT_NEW_S3_PREFIX_WITH_OWN_GENESIS_AND_CHAIN",
            "active_monitoring":"NEW_EPOCH_SPECIFIC_METRICS_AND_RULES_REVIEW_REQUIRED",
            "isolation":"ST_ONLY_NO_PROD_NO_BROKER",
            "qualification":"REQUIRES_NEW_FORWARD_SESSIONS_BEFORE_GREEN",
        },
        "deployment_authorized":False,
        "new_genesis_written":False,
        "paper_replayed":False,
        "old_book_mutated":False,
        "aws_mutations":False,
        "lambda_invocations":False,
        "broker_orders":False,
        "blocking_gates":[
            "REVIEW_PRIVATE_HANDLER_AND_WATCHDOG_CHANGES_AS_ONE_RELEASE",
            "BUILD_NEW_EPOCH_S3_NAMESPACE_AND_IDEMPOTENT_GENESIS_GATES",
            "NEW_MONITORING_MUST_NOT_REINTERPRET_HISTORIC_ALARMS_AS_PASS",
            "SEPARATE_ST_CODE_RELEASE_AND_CFN_DRIFT_RECONCILIATION",
            "STAGE_SAFELY_WITH_TESTS_THEN_FIRST_REAL_PROSPECTIVE_RECEIPT",
        ],
        "accounting_truth":"STRUCTURAL_HASH_LINKS_ONLY_NOT_ECONOMIC_NAV_AUDIT",
    }


def inspect(clients):
    release_result=release.check_readonly(clients)
    require(release_result.get("current_all_candidate") is True and
            release_result.get("mixed_or_partial_code") is False and
            release_result.get("prod_schedules_all_disabled") is True and
            release_result.get("blocked_cfn_change_set",{}).get("status")==
            "RETIRED_NOT_EXECUTED",
            "POSTDEPLOY_ST_CODE_PROD_ISOLATION_UNVERIFIED")
    s3=clients["s3"]
    proof=immutable.chain_report(s3)
    old_book_verified(proof)
    historic_pins=prove_historic_anchors(s3)
    prior=prior_signal_proof(s3)
    cal=next_market_session_proof()
    return proposal(proof,historic_pins,cal,prior)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--plan",action="store_true")
    args=parser.parse_args()
    require(args.plan,"MUST_USE_--plan_READ_ONLY")
    import boto3
    session=boto3.session.Session(region_name=release.REGION)
    clients={name:session.client(name) for name in
             ("sts","lambda","events","cloudformation","s3")}
    result=inspect(clients)
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status":"BLOCKED_NO_MUTATIONS",
                          "reason_type":type(exc).__name__,
                          "reason":str(exc)[:220],
                          "aws_mutations":False,"lambda_invocations":False,
                          "broker_orders":False,"paper_backfill":False}))
        raise SystemExit(2)

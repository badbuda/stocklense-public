"""SL-56 Nov12 prospective Paper epoch—no retroactive opening or unverified NAV.

Pure policy. This does NOT authorize AWS execution; a separate guarded private
adapter, source attestation, original-old-book hash proof, explicit operator
pre-open approval, and independent market 1m evidence are still required.
"""
import pytest

from stocklens import paper_epoch3 as epoch


def plan():
    return {
        "status":"FORWARD_ONLY_EPOCH_RECOVERY_PROPOSAL_NOT_DEPLOYABLE",
        "deployment_authorized":False,
        "aws_mutations":False,"broker_orders":False,
        "new_genesis_written":False,"paper_replayed":False,
        "old_book_mutated":False,
        "old_epoch":{
            "book_id":epoch.OLD_BOOK,
            "last_qualified_session":epoch.LAST_OLD_DAY,
            "genesis_and_links":"ALL_MATCH",
            "archived_immutable_anchor_sha256":dict(epoch.HISTORIC_SHA256),
            "state":"BREACHED_AND_PRESERVED_UNCHANGED",
            "historical_alarm_truth":"PRESERVE_HISTORIC_FAIL_CLOSED",
        },
        "unqualified_sessions":[{
            "session":s,"proposed_gap_status":"MISSED_UNRECOVERABLE_NO_BACKFILL",
            "old_paper_receipt":"MISSING_AND_MUST_REMAIN_MISSING",
            "old_continuity":"MISSING_AND_MUST_REMAIN_MISSING",
            "broker_execution_claim":False,
        } for s in epoch.MISSED],
        "new_epoch":{
            "proposed_book_id":epoch.NEW_BOOK,
            "proposed_first_exchange_session":epoch.FIRST_NEW_DAY,
            "initial_NAV":"NO_VALUE_ASSIGNED_OR_INFERRED",
            "ledger":"DISTINCT_NEW_S3_PREFIX_WITH_OWN_GENESIS_AND_CHAIN",
        },
    }


def inputs():
    return {
        "verified_prior_signal":{
            "session":"2026-11-11","mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
            "broker_actions_enabled":False,"version_id_present":True,
            "sha256":"a"*64,"archived_at_utc":"2026-11-12T08:31:00Z",
        },
        "execution_market":{
            "session":"2026-11-12","mode":"CLOSED_REGULAR_XNYS",
            "broker_orders_enabled":False,
            "independent_vendor_close_verified":True,
            "near_session_close_present":True,
            "duplicate_bars_present":False,
            "minute_bars":{"QQQ":390,"TQQQ":390},
        },
        "inception":{
            "operator_approved":True,
            "approved_at_utc":"2026-11-11T15:30:00Z",
            "source":"NEW_INDEPENDENT_SIMULATED_CAPITAL_NO_OLD_NAV_TRANSFER",
            "old_book_inherited":False,
            "initial_shares":{"QQQ":0,"TQQQ":0},
            "starting_cash_usd":100000,
        },
        "now_utc":"2026-11-12T22:00:00Z",
    }


def test_exact_first_future_session_and_all_old_gaps_preserved():
    assert epoch.FIRST_NEW_DAY == "2026-11-12"
    assert epoch.PREVIOUS_SIGNAL_DAY == "2026-11-11"
    assert epoch.LAST_OLD_DAY == "2026-11-04"
    assert list(epoch.MISSED) == [
        "2026-11-05","2026-11-06","2026-11-09",
        "2026-11-10","2026-11-11",
    ]
    p=epoch.pinned_xnys_session()
    assert p["opening_utc"]=="2026-11-12T14:30:00Z"
    assert p["closing_utc"]=="2026-11-12T21:00:00Z"
    assert p["prior_exchange_session"] == "2026-11-11"


def test_valid_offline_prospective_candidate_never_approves_aws_writes():
    r=epoch.assess_bootstrap_candidate(plan(),**inputs())
    assert r["status"] == "OFFLINE_EPOCH3_CANDIDATE_POLICY_PASS_NOT_AWS_ACCEPTANCE"
    assert r["candidate_manifest"]["book"]==epoch.NEW_BOOK
    assert r["candidate_manifest"]["old_nav_transferred"] is False
    assert r["candidate_manifest"]["recorded_gaps"] == list(epoch.MISSED)
    assert r["new_epoch_genesis_committed"] is False
    assert r["aws_mutations"] is False
    assert r["broker_orders"] is False
    assert r["candidate_manifest"]["first_session"] == "2026-11-12"


@pytest.mark.parametrize("approved_at",[
    "2026-11-12T14:30:00Z","2026-11-12T16:00:00Z"
])
def test_after_open_approval_cannot_retroactively_start_new_book(approved_at):
    i=inputs()
    i["inception"]["approved_at_utc"]=approved_at
    with pytest.raises(epoch.EpochPolicyError,match="RETROACTIVE_INCEPTION_APPROVAL"):
        epoch.assess_bootstrap_candidate(plan(),**i)


@pytest.mark.parametrize("signal_at",[
    "2026-11-11T20:59:00Z","2026-11-12T14:30:00Z",
])
def test_decision_signal_must_be_between_previous_close_and_new_open(signal_at):
    i=inputs()
    i["verified_prior_signal"]["archived_at_utc"]=signal_at
    with pytest.raises(epoch.EpochPolicyError,match="LOOKAHEAD_OR_SAME_SESSION_SIGNAL"):
        epoch.assess_bootstrap_candidate(plan(),**i)


def test_nov12_paper_cannot_exist_before_actual_close():
    i=inputs()
    i["now_utc"]="2026-11-12T20:59:00Z"
    with pytest.raises(epoch.EpochPolicyError,match="CANNOT_PREQUALIFY_FUTURE_PAPER_SESSION"):
        epoch.assess_bootstrap_candidate(plan(),**i)


def test_385_bar_boundary_and_real_both_symbols():
    i=inputs()
    i["execution_market"]["minute_bars"]["QQQ"]=384
    with pytest.raises(epoch.EpochPolicyError,match="NOT_ENOUGH_UNIQUE_MINUTE_BARS"):
        epoch.assess_bootstrap_candidate(plan(),**i)


def test_no_fabricated_gap_and_no_old_nav_transfer():
    p=plan()
    p["unqualified_sessions"].pop()
    with pytest.raises(epoch.EpochPolicyError,match="OLD_BOOK_OR_ARCHIVE_ANCHORS_NOT_VERIFIED|GAP_DAYS_DIFFER"):
        epoch.assess_bootstrap_candidate(p,**inputs())
    i=inputs()
    i["inception"]["old_book_inherited"]=True
    with pytest.raises(epoch.EpochPolicyError,match="UNAPPROVED_OR_BRIDGED_NAV"):
        epoch.assess_bootstrap_candidate(plan(),**i)


def test_if_nov12_is_missed_do_not_bootstrap_later_using_this_name():
    i=inputs()
    i["now_utc"]="2026-11-16T22:00:00Z"
    i["inception"]["approved_at_utc"]="2026-11-16T10:00:00Z"
    with pytest.raises(epoch.EpochPolicyError,match="RETROACTIVE_INCEPTION_APPROVAL"):
        epoch.assess_bootstrap_candidate(plan(),**i)

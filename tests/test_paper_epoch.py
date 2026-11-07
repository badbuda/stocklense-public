"""Adversarial tests: a gap is never a fill; offline policy isn't AWS acceptance."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import pytest
from pathlib import Path

from stocklens import paper_epoch as ep


def valid_plan():
    return {
        "status":"FORWARD_ONLY_EPOCH_RECOVERY_PROPOSAL_NOT_DEPLOYABLE",
        "deployment_authorized":False,
        "aws_mutations":False,"broker_orders":False,
        "new_genesis_written":False,"paper_replayed":False,
        "old_book_mutated":False,
        "old_epoch":{
            "book_id":ep.OLD_BOOK,
            "last_qualified_session":ep.LAST_OLD_DAY,
            "genesis_and_links":"ALL_MATCH",
            "archived_immutable_anchor_sha256":dict(ep.HISTORIC_SHA256),
            "state":"BREACHED_AND_PRESERVED_UNCHANGED",
            "historical_alarm_truth":"PRESERVE_HISTORIC_FAIL_CLOSED",
        },
        "unqualified_sessions":[
            {"session":day,"proposed_gap_status":"MISSED_UNRECOVERABLE_NO_BACKFILL",
             "old_paper_receipt":"MISSING_AND_MUST_REMAIN_MISSING",
             "old_continuity":"MISSING_AND_MUST_REMAIN_MISSING",
             "broker_execution_claim":False} for day in ep.MISSED
        ],
        "new_epoch":{
            "proposed_book_id":ep.NEW_BOOK,
            "proposed_first_exchange_session":ep.FIRST_NEW_DAY,
            "initial_NAV":"NO_VALUE_ASSIGNED_OR_INFERRED",
            "ledger":"DISTINCT_NEW_S3_PREFIX_WITH_OWN_GENESIS_AND_CHAIN",
        },
    }


def inputs():
    return {
        "verified_prior_signal":{
            "session": "2026-11-06",
            "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
            "broker_actions_enabled":False,
            "version_id_present":True,
            "sha256":"a"*64,
            "archived_at_utc":"2026-11-07T03:25:00Z",
        },
        "execution_market":{
            "session":"2026-11-09",
            "mode":"CLOSED_REGULAR_XNYS",
            "broker_orders_enabled":False,
            "independent_vendor_close_verified":True,
            "near_session_close_present":True,
            "duplicate_bars_present":False,
            "minute_bars":{"QQQ":390,"TQQQ":389},
        },
        "inception":{
            "operator_approved":True,
            "approved_at_utc":"2026-11-08T10:00:00Z",
            "source":"NEW_INDEPENDENT_SIMULATED_CAPITAL_NO_OLD_NAV_TRANSFER",
            "old_book_inherited":False,
            "initial_shares":{"QQQ":0,"TQQQ":0},
            "starting_cash_usd":100000.00,
        },
        "now_utc":"2026-11-09T22:30:00Z",
    }


def test_nov9_is_pinned_actual_exchange_day_without_optional_package():
    result=ep.pinned_xnys_session()
    assert result["status"]=="PINNED_NYSE_NOV09_REGULAR_SESSION_2026_ONLY"
    assert result["opening_utc"]=="2026-11-09T14:30:00Z"
    assert result["closing_utc"]=="2026-11-09T21:00:00Z"
    assert result["no_general_calendar_claim"] is True


def test_valid_future_offline_case_is_not_a_deployment_or_economic_attestation():
    data=ep.assess_bootstrap_candidate(valid_plan(), **inputs())
    assert data["status"]=="OFFLINE_EPOCH2_CANDIDATE_POLICY_PASS_NOT_AWS_ACCEPTANCE"
    assert data["broker_orders"] is False
    assert data["aws_mutations"] is False
    assert data["paper_backfill"] is False
    assert data["new_epoch_genesis_committed"] is False
    assert data["watchdog_green"] is False
    assert data["original_epoch_alarm_state"]=="PRESERVE_FAIL_CLOSED"
    assert data["new_epoch_monitor_state"]=="NOT_STARTED_UNVERIFIED"
    assert data["prior_source_provenance_independently_verified"] is False
    manifest=data["candidate_manifest"]
    assert manifest["old_nav_transferred"] is False
    assert manifest["performance_epoch_reset"] is True
    assert manifest["new_prefix"] != "paper/"
    assert "epochs/" in manifest["new_prefix"]
    assert list(manifest["recorded_gaps"])==list(ep.MISSED)
    assert len(data["candidate_manifest_sha256"])==64


def test_source_hash_deterministic_for_exact_evidence():
    args=inputs()
    assert ep.assess_bootstrap_candidate(valid_plan(),**args)[
        "candidate_manifest_sha256"] == ep.assess_bootstrap_candidate(
        valid_plan(),**args)["candidate_manifest_sha256"]


@pytest.mark.parametrize("field,value",[
    ("status","PASS"),
    ("deployment_authorized",True),
    ("aws_mutations",True),
    ("broker_orders",True),
    ("new_genesis_written",True),
    ("paper_replayed",True),
    ("old_book_mutated",True),
])
def test_attempt_to_relabel_historic_plan_is_blocked(field,value):
    p=valid_plan()
    p[field]=value
    with pytest.raises(ep.EpochPolicyError):
        ep.old_epoch_attested(p)


@pytest.mark.parametrize("mode,value",[
    ("rewrite_history","NO"),
    ("missing_one","NO"),
    ("move_genesis","NO"),
    ("new_book_old_name","NO"),
    ("fake_missed_fills","NO")
])
def test_broken_gaps_anchors_or_names_fail_closed(mode,value):
    p=valid_plan()
    if mode=="rewrite_history":
        p["old_epoch"]["archived_immutable_anchor_sha256"][
            "paper/sessions/2026-11-04.json"]="b"*64
    if mode=="missing_one":
        p["unqualified_sessions"].pop()
    if mode=="move_genesis":
        p["old_epoch"]["last_qualified_session"]="2026-11-05"
    if mode=="new_book_old_name":
        p["new_epoch"]["proposed_book_id"]=ep.OLD_BOOK
    if mode=="fake_missed_fills":
        p["unqualified_sessions"][0]["broker_execution_claim"]=True
    with pytest.raises(ep.EpochPolicyError):
        ep.old_epoch_attested(p)


@pytest.mark.parametrize("timestamp",[
    "2026-11-09T20:59:59Z","2026-11-07T20:00:00Z",
    "2026-11-09T15:00:00+01:00","bad","2026-11-09T21:00:00Z",
])
def test_no_early_or_incorrectly_timed_approved_execution(timestamp):
    args=inputs()
    args["now_utc"]=timestamp
    with pytest.raises(ep.EpochPolicyError):
        ep.assess_bootstrap_candidate(valid_plan(),**args)


@pytest.mark.parametrize("archived",[
    "2026-11-09T14:30:00Z","2026-11-09T15:00:00Z",
    "2026-11-10T02:00:00Z"
])
def test_stale_or_late_prior_signal_never_used_for_next_open(archived):
    args=inputs()
    args["verified_prior_signal"]["archived_at_utc"]=archived
    with pytest.raises(ep.EpochPolicyError,match="LOOKAHEAD_OR_SAME_SESSION_SIGNAL"):
        ep.assess_bootstrap_candidate(valid_plan(),**args)


@pytest.mark.parametrize("field,value",[
    ("session","2026-11-08"),
    ("mode","LIVE_BROKER"),
    ("broker_actions_enabled",True),
    ("version_id_present",False),
    ("sha256","0"),
])
def test_signal_must_be_frozen_nobroker_versioned_and_prehash(field,value):
    args=inputs()
    args["verified_prior_signal"][field]=value
    with pytest.raises(ep.EpochPolicyError):
        ep.assess_bootstrap_candidate(valid_plan(),**args)


@pytest.mark.parametrize("field,value",[
    ("session","2026-11-06"),
    ("mode","AFTER_HOURS"),
    ("broker_orders_enabled",True),
    ("independent_vendor_close_verified",False),
    ("near_session_close_present",False),
    ("duplicate_bars_present",True),
    ("minute_bars",{"QQQ":385,"TQQQ":384}),
    ("minute_bars",{"QQQ":390,"TQQQ":391}),
    ("minute_bars",{"QQQ":390,"TQQQ":True}),
])
def test_market_integrity_must_fail_closed(field,value):
    args=inputs()
    args["execution_market"][field]=value
    with pytest.raises(ep.EpochPolicyError):
        ep.assess_bootstrap_candidate(valid_plan(),**args)


@pytest.mark.parametrize("field,value",[
    ("operator_approved",False),
    ("source","OLD_NAV"),
    ("old_book_inherited",True),
    ("initial_shares",{"QQQ":42,"TQQQ":0}),
    ("starting_cash_usd",0),
    ("starting_cash_usd",float("nan")),
    ("starting_cash_usd",-200),
    ("starting_cash_usd",True),
    ("approved_at_utc","2026-11-09T14:31:00Z"),
])
def test_inception_cannot_inherit_undocumented_nav_or_be_retroactive(field,value):
    args=inputs()
    args["inception"][field]=value
    with pytest.raises(ep.EpochPolicyError):
        ep.assess_bootstrap_candidate(valid_plan(),**args)


def test_monitor_old_and_new_epochs_never_conflate():
    result=ep.monitor_partition(
        original_missing=True,prospective_receipt_qualified=False,
        new_genesis_verified=False)
    assert result["original_epoch_status"]=="FAIL_CLOSED_HISTORIC_GAP"
    assert result["new_epoch_status"]=="NOT_QUALIFIED"
    assert result["historical_missing_receipts_stay_missing"] is True
    assert result["cross_epoch_aggregate_nav_authorized"] is False
    assert result["can_manually_clear_old_alarm"] is False
    assert result["real_watchdog_changed"] is False


def test_monitor_pure_status_does_not_reset_old_alarm_even_if_new_qualified():
    result=ep.monitor_partition(
        original_missing=True,prospective_receipt_qualified=True,
        new_genesis_verified=True)
    assert result["original_epoch_status"]=="FAIL_CLOSED_HISTORIC_GAP"
    assert result["can_manually_clear_old_alarm"] is False
    assert result["real_watchdog_changed"] is False


def test_importable_policy_does_not_use_any_aws_or_broker_api():
    source=Path("stocklens/paper_epoch.py").read_text()
    for forbidden in (
        "import boto3", "from boto3", "requests.", "urlopen(",
        ".put_object(", ".delete_object(", ".invoke(", ".put_item(",
        ".execute_change_set(", ".update_function_code(",
        ".set_alarm_state(", ".enable_rule(", ".disable_rule(",
    ):
        assert forbidden not in source

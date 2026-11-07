"""ST Paper gap epoch proposal must never invent fills, reset alerts, or mutate AWS."""
from __future__ import annotations

import copy
from pathlib import Path
import pytest

from infra.aws import st_paper_forward_epoch_plan_readonly as m


def chain():
    days=("2026-10-30","2026-11-02","2026-11-03","2026-11-04")
    day_checks={}
    for day in days:
        day_checks[day]={
            "sessions":{
                "status":"IMMUTABLE_VERSIONED_OBJECT_PRESENT",
                "book_field":"MATCH","session_field":"MATCH",
                "state_last_mark_session":"MATCH","shadow_mode":"MATCH",
                "broker_fills_observed_false":True,
                "broker_orders_authorized_false":True,
            },
            "continuity":{
                "status":"IMMUTABLE_VERSIONED_OBJECT_PRESENT",
                "continuity_status":"ON_TIME_QUALIFIED",
                "qualified_in_record":True,
                "book_field":"MATCH", "session_field":"MATCH",
                "paper_hash_attested":"MATCH","paper_key_attested":"MATCH",
                "paper_version_attested":"MATCH",
                "broker_orders_false":True,"broker_fills_false":True,
            }}
    for d in m.MISSING:
        day_checks[d]={"sessions":"MISSING","continuity":"MISSING"}
    return {
        "genesis":{"book_matches":"MATCH",
                   "initial_paper_link":"MATCH",
                   "initial_continuity_link":"MATCH"},
        "stored_hash_linkage":[
            {"previous_session":a, "session":b,
             "paper_prior_receipt_link":"MATCH",
             "continuity_previous_record_link":"MATCH"}
            for a,b in zip(days[:-1],days[1:])],
        "versioned_daily_records":day_checks,
        "missing_dates":list(m.MISSING),
        "original_economic_accounting_status":"NOT_ATTESTED_BY_HASH_LINKS",
    }


def test_plan_preserves_original_epoch_and_missing_sessions():
    report=m.proposal(
        chain(),{k:{"sha256":sha,"s3_version_id_verified":True}
                 for k,sha in m.SOURCE_PINS.items()},
        {"status":"XNYS_NEXT_SESSION_VERIFIED"},
        {"status":"VERSIONED_FROZEN_NONBROKER_SIGNAL_READ"})
    assert report["status"]=="FORWARD_ONLY_EPOCH_RECOVERY_PROPOSAL_NOT_DEPLOYABLE"
    assert report["deployment_authorized"] is False
    assert report["new_genesis_written"] is False
    assert report["broker_orders"] is False
    assert report["old_book_mutated"] is False
    assert report["aws_mutations"] is False
    assert report["old_epoch"]["historical_alarm_truth"]=="PRESERVE_HISTORIC_FAIL_CLOSED"
    assert report["new_epoch"]["initial_NAV"]=="NO_VALUE_ASSIGNED_OR_INFERRED"
    assert report["new_epoch"]["proposed_first_exchange_session"]=="2026-11-09"
    assert [d["session"] for d in report["unqualified_sessions"]]==list(m.MISSING)
    assert all(d["old_paper_receipt"]=="MISSING_AND_MUST_REMAIN_MISSING"
               for d in report["unqualified_sessions"])
    assert all(d["broker_execution_claim"] is False
               for d in report["unqualified_sessions"])


@pytest.mark.parametrize("tamper",[
    lambda c: c["genesis"].update({"initial_paper_link":"DOES_NOT_MATCH"}),
    lambda c: c["stored_hash_linkage"][2].update(
        {"paper_prior_receipt_link":"DOES_NOT_MATCH"}),
    lambda c: c["stored_hash_linkage"][1].update(
        {"continuity_previous_record_link":"DOES_NOT_MATCH"}),
    lambda c: c.update({"missing_dates":["2026-11-05"]}),
    lambda c: c["versioned_daily_records"]["2026-11-04"]["continuity"].update(
        {"continuity_status":"MISSED_UNRECOVERABLE"}),
    lambda c: c["versioned_daily_records"]["2026-11-03"]["sessions"].update(
        {"broker_orders_authorized_false":False}),
    lambda c: c["versioned_daily_records"]["2026-11-02"]["continuity"].update(
        {"paper_version_attested":"MISMATCH"}),
])
def test_any_historic_sha_or_qualification_gap_fails_closed(tamper):
    example=chain()
    tamper(example)
    with pytest.raises(RuntimeError):
        m.old_book_verified(example)


def test_historic_anchors_pin_the_three_exact_stored_object_versions(monkeypatch):
    expected=m.SOURCE_PINS
    class S3: pass
    monkeypatch.setattr(m.immutable,"stable_object",
                        lambda s,key:{"sha":expected[key],"version":"IMMUTABLE_VERSION"})
    report=m.prove_historic_anchors(S3())
    assert len(report)==3
    assert set(report)==set(expected)
    monkeypatch.setattr(m.immutable,"stable_object",
                        lambda s,key:{"sha":"0"*64})
    with pytest.raises(RuntimeError,match="HISTORIC_ARCHIVE_PIN_CHANGED"):
        m.prove_historic_anchors(S3())


def test_signal_provenance_has_no_broker_permission_and_matches_prior_day(monkeypatch):
    class S3: pass
    proof={"payload":{
        "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
        "execution_plan":{"broker_actions_enabled":False},
        "latest":{"asof_date":"2026-11-06"},
    },"sha":"a"*64}
    monkeypatch.setattr(m.immutable,"stable_object",lambda s,key:proof)
    result=m.prior_signal_proof(S3())
    assert result["session"]=="2026-11-06"
    assert result["timing_before_next_market_open"]=="NOT_ATTESTED_HERE"
    assert result["market_data_completeness"]=="NOT_ATTESTED_HERE"
    proof["payload"]["execution_plan"]["broker_actions_enabled"]=True
    with pytest.raises(RuntimeError,match="PRIOR_SIGNAL_MIGHT_ENABLE_BROKER"):
        m.prior_signal_proof(S3())


def test_release_gate_blocks_stale_or_partially_deployed_runtime(monkeypatch):
    monkeypatch.setattr(m.release,"check_readonly",lambda c:{
        "current_all_candidate":False,
        "mixed_or_partial_code":True,
        "prod_schedules_all_disabled":True,
        "blocked_cfn_change_set":{"status":"RETIRED_NOT_EXECUTED"},
    })
    with pytest.raises(RuntimeError,match="POSTDEPLOY_ST_CODE_PROD_ISOLATION_UNVERIFIED"):
        m.inspect({})


def test_inspect_does_not_authorize_writes(monkeypatch):
    monkeypatch.setattr(m.release,"check_readonly",lambda c:{
        "current_all_candidate":True,
        "mixed_or_partial_code":False,
        "prod_schedules_all_disabled":True,
        "blocked_cfn_change_set":{"status":"RETIRED_NOT_EXECUTED"},
    })
    monkeypatch.setattr(m.immutable,"chain_report",lambda s:chain())
    monkeypatch.setattr(m,"prove_historic_anchors",
                        lambda s:{k:{"sha256":v} for k,v in m.SOURCE_PINS.items()})
    monkeypatch.setattr(m,"prior_signal_proof",
                        lambda s:{"status":"VERSIONED_FROZEN_NONBROKER_SIGNAL_READ"})
    monkeypatch.setattr(m,"next_market_session_proof",
                        lambda :{"status":"XNYS_CALENDAR_NOT_AVAILABLE_REVIEW_REQUIRED"})
    report=m.inspect({"s3":object()})
    assert report["deployment_authorized"] is False
    assert report["new_genesis_written"] is False
    assert report["paper_replayed"] is False
    assert report["aws_mutations"] is False
    assert report["lambda_invocations"] is False
    assert report["old_epoch"]["state"]=="BREACHED_AND_PRESERVED_UNCHANGED"


def test_source_never_mutates_cfn_lambda_s3_alarms_broker():
    source=Path("infra/aws/st_paper_forward_epoch_plan_readonly.py").read_text()
    banned=(
        ".invoke(", ".put_object(", ".delete_object(", ".put_item(",
        ".update_function_code(", ".update_stack(",
        ".set_alarm_state(", ".execute_change_set(", ".disable_rule(",
        ".enable_rule(", ".create_change_set(", ".put_metric_alarm(",
    )
    assert all(fragment not in source for fragment in banned)

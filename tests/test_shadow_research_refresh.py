"""Offline falsification of bounded source-refresh; never calls Yahoo or AWS."""
from copy import deepcopy
import pytest
from shadow_research_refresh import reconcile


def pair():
    d = {
        "asof_date":"2026-10-16", "level":3, "defense_active":False,
        "target_leverage":3.0, "qqq_weight":0.0,"tqqq_weight":0.985,
        "invested_fraction":0.985,"qqq_adjusted_close":709.8,
        "decision_source":"stocklens.core.replay_levels",
    }
    report={"status":"PASS","observed_instruments":["QQQ","TQQQ"],
            "period":{"end":"2026-10-16"},"latest_frozen_decision":d}
    signal={"mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
            "state_replay":"EXACT_FROM_2009_09_01_WITH_PRESTART_WARMUP",
            "latest":{**d,"features":{"close":709.8}},
            "data_audit":{"last_close":709.8},
            "execution_plan":{"broker_actions_enabled":False}}
    return report, signal


def test_already_matching_never_downloads():
    report,signal=pair()
    seen=[]
    result=reconcile(lambda:report,signal,lambda:seen.append("network"),
                     lambda _:seen.append("wait"))
    assert result["status"]=="PASS"
    assert seen==[]


def test_stale_observed_tqqq_recovers_only_after_recomputing_real_report():
    report,signal=pair()
    stale=deepcopy(report)
    stale["period"]["end"]="2026-10-15"
    stale["latest_frozen_decision"]["asof_date"]="2026-10-15"
    stale["latest_frozen_decision"]["qqq_adjusted_close"]=728.0
    rows=[stale,report]
    downloads=[]
    result=reconcile(lambda:rows[0],signal,lambda:(downloads.append(1),rows.pop(0)),
                     lambda _:None,max_rebuilds=1)
    assert result["status"]=="PASS"
    assert len(downloads)==1


def test_non_temporal_policy_mismatch_halts_without_retry():
    report,signal=pair()
    signal["latest"]["target_leverage"]=1.25
    calls=[]
    with pytest.raises(RuntimeError,match="NON_RETRYABLE_FROZEN_RESEARCH_PARITY"):
        reconcile(lambda:report,signal,lambda:calls.append("DOWNLOAD"),lambda _:None)
    assert calls==[]


def test_no_synthetic_equality_when_vendor_stays_stale():
    report,signal=pair()
    report["period"]["end"]="2026-10-15"
    report["latest_frozen_decision"]["asof_date"]="2026-10-15"
    downloads=[]; waits=[]
    with pytest.raises(RuntimeError,match="UNRESOLVED_NO_PUBLICATION"):
        reconcile(lambda:report,signal,lambda:downloads.append(1),
                  lambda delay:waits.append(delay),max_rebuilds=3)
    assert len(downloads)==3
    assert waits==[90,90]


def test_source_revision_price_drift_not_waived():
    report,signal=pair()
    report["latest_frozen_decision"]["qqq_adjusted_close"]=709.81
    with pytest.raises(RuntimeError,match="UNRESOLVED_NO_PUBLICATION"):
        reconcile(lambda:report,signal,lambda:None,lambda _:None,max_rebuilds=1)


def test_unexpected_broker_permission_halts_immediately():
    report,signal=pair()
    signal["execution_plan"]["broker_actions_enabled"]=True
    with pytest.raises(RuntimeError,match="NON_RETRYABLE_FROZEN_RESEARCH_PARITY"):
        reconcile(lambda:report,signal,lambda:None,lambda _:None,max_rebuilds=1)

"""A stale Paper source MUST NEVER become a green operational report."""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from stocklens_closeout import SOURCE, load, evaluate, build

def inputs():
    return load(Path("."))

def test_real_project_evidence_stays_operationally_blocked():
    source, hashes = inputs()
    r = evaluate(source,hashes)
    assert r["overall"] == "BLOCKED_OPERATIONAL_NOT_RESEARCH"
    assert r["automated_live_trading_authorized"] is False
    assert r["broker_orders"] is False
    assert r["automatic_model_promotion"] is False
    assert r["components"]["historical_combination_research"]["arm_count"] == 56
    assert r["components"]["historical_combination_research"]["stress_tests"] == 224
    assert r["components"]["aws_st"]["status"] == "NOT_VERIFIED_FROM_GITHUB"
    assert r["components"]["aws_prod"]["status"] == "NOT_VERIFIED_FROM_GITHUB"
    assert r["components"]["legacy_paper"]["independent_broker_fills"] is False
    assert r["components"]["readiness"]["blocked"] > 0

def test_matching_paper_date_does_not_create_an_aws_proof():
    d,h=inputs()
    d=deepcopy(d)
    d["paper"]["latest_session"]=d["signals"]["updated_session"]
    out=evaluate(d,h)
    assert out["components"]["legacy_paper"]["status"]=="DATE_MATCH_ONLY_NOT_AWS_VERIFIED"
    assert out["components"]["aws_prod"]["status"]=="NOT_VERIFIED_FROM_GITHUB"
    assert out["overall"]!="PASS"

def test_missing_or_divergent_frozen_evidence_fails_closed():
    d,h=inputs()
    for key,bad in [
        ("readiness",lambda x: x.update(passed_count=999)),
        ("combinations",lambda x: x.update(automatic_promotion=True)),
        ("paper",lambda x: x.update(broker_fills_observed=True)),
        ("signals",lambda x: x.update(instruments=["QQQ","SYNTHETIC_TQQQ"])),
        ("forward",lambda x: x.update(backfill_authorized=True)),
    ]:
        candidate=deepcopy(d)
        bad(candidate[key])
        with pytest.raises(ValueError):
            evaluate(candidate,h)

def test_no_implicit_paper_catchup_and_date_gaps():
    d,h=inputs()
    assert evaluate(d,h)["components"]["legacy_paper"]["status"]=="STALE"
    candidate=deepcopy(d)
    candidate["forward"]["paper_sessions"] += 1
    with pytest.raises(ValueError,match="PAPER_SESSION_COUNTS_DISAGREE"):
        evaluate(candidate,h)
    candidate=deepcopy(d)
    candidate["forward"]["current_signal_date"]="2026-01-01"
    with pytest.raises(ValueError,match="FORWARD_SIGNAL_SOURCE_INCONSISTENT"):
        evaluate(candidate,h)

def test_missing_source_never_backfills(tmp_path):
    with pytest.raises(FileNotFoundError):
        load(tmp_path)

def test_build_report_roundtrip(tmp_path):
    d,_=inputs()
    for path in SOURCE.values():
        f=tmp_path/path
        f.parent.mkdir(parents=True,exist_ok=True)
        f.write_text(json.dumps(d[next(k for k,v in SOURCE.items() if v==path)]))
    out=build(tmp_path)
    data=json.loads((tmp_path/"docs/stocklens-closeout.json").read_text())
    assert out["overall"]==data["overall"]
    md=(tmp_path/"docs/stocklens-closeout.md").read_text()
    assert "AWAITING" in md or "NOT_VERIFIED" in md
    assert "PAPER_FORWARD_CHAIN" in md

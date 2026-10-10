"""Adversarial P0: never promote partial, mismatched or spoofed LEAN parity."""
from __future__ import annotations
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from qc_input_ingestion import (validate_export, transition_hash,
                                original_daily_leverage_hash, original_session_dates_hash)
from qc_same_input_parity import compare
from qc_original_lean_chart_audit import extract, compare_original_vs_execution_proxy


HEADERS=["date","close","sma50","sma200","vol20","mom12","level","defense","leverage"]


def test_one_row_can_never_be_certified_as_full_lean_parity(tmp_path):
    p=tmp_path/"qc_lean_daily_features.csv"
    p.write_text(",".join(HEADERS)+"\n2024-08-29,100,90,80,.2,.1,3,false,3\n")
    out=tmp_path/"same.json"
    r=compare(path=p,out=out)
    assert r["status"]=="BLOCKED_INVALID_LEAN_EXPORT"
    assert not r["same_input_parity_proven"]
    assert r["compared_sessions"]==0
    assert "SESSION_COUNT" in r["input_validation"]["errors"]


def fixture(tmp_path):
    dates=["2009-09-01","2009-09-02","2009-09-03"]
    data=[
      ["2009-09-01","100","95","93",".21",".2","3","false","3"],
      ["2009-09-02","101","95","93",".22",".3","3","false","3"],
      ["2009-09-03","99","95","93",".23",".1","2","false","2"],
    ]
    schema={"required_columns":HEADERS,"expected_sessions":3,
            "first_date":dates[0],"last_date":dates[-1]}
    transition=[["2009-09-01",3],["2009-09-03",2]]
    golden={"sessions":3,"transitions":transition,
            "transition_sha256":transition_hash(transition)}
    state={"sessions":3,"leverage_counts":{"3.0":2,"2.0":1},
           "first_time_utc":"2009-09-01T20:01:00Z",
           "last_time_utc":"2009-09-03T20:01:00Z",
           "max_drawdown_pct":-3,"last_nav_multiple":1.10}
    state["daily_date_leverage_sha256"]=original_daily_leverage_hash(
        [{"date":r[0], "leverage":float(r[8])} for r in data])
    state["daily_session_dates_sha256"]=original_session_dates_hash(dates)
    paths={}
    for k,rows in [("schema",schema),("golden",golden),("state",state)]:
        paths[k]=tmp_path/(k+".json")
        paths[k].write_text(json.dumps(rows))
    paths["csv"]=tmp_path/"features.csv"
    def write(rows):
        with paths["csv"].open("w",newline="") as f:
            writer=csv.writer(f);writer.writerow(HEADERS);writer.writerows(rows)
    write(data)
    return paths,data,write


def check(paths):
    return validate_export(paths["csv"],paths["schema"],paths["golden"],paths["state"])


def test_valid_structure_does_not_prove_native_source_authenticity(tmp_path):
    paths,data,write=fixture(tmp_path)
    out=check(paths)
    assert out["status"]=="VALID"
    assert out["rows"]==3
    assert out["source_authenticity_proven"] is False
    assert out["same_input_parity_ready"] is True


def test_fake_states_or_bad_features_rejected(tmp_path):
    paths,data,write=fixture(tmp_path)
    changed=[r.copy() for r in data]
    changed[2][8]="3"  # illegal vs 2x level, and original golden transition
    write(changed)
    out=check(paths)
    assert out["status"]=="INVALID"
    assert any("INVALID_ROW" in x for x in out["errors"])
    changed=[r.copy() for r in data]
    changed[0][4]="nan"
    write(changed)
    assert check(paths)["status"]=="INVALID"
    changed=[r.copy() for r in data]
    changed[0][0]=changed[1][0]  # duplicate date
    write(changed)
    assert check(paths)["status"]=="INVALID"
    changed=[r.copy() for r in data]
    changed[1][8]="2"
    changed[1][6]="2"
    write(changed)
    assert "FROZEN_TRANSITION_DRIFT" in check(paths)["errors"]


def test_calendar_swapping_is_rejected_even_when_transitions_and_counts_match(tmp_path):
    paths, data, write = fixture(tmp_path)
    # Three sequential state dates cannot be changed without a duplicate.
    # Widen the interval while preserving first/last state and transition dates.
    data[2][0] = "2009-09-08"
    data[1][0] = "2009-09-03"
    write(data)
    state=json.loads(paths["state"].read_text())
    state["daily_date_leverage_sha256"]=original_daily_leverage_hash(
        [{"date":r[0], "leverage":float(r[8])} for r in data])
    state["daily_session_dates_sha256"]=original_session_dates_hash([r[0] for r in data])
    state["last_time_utc"]="2009-09-08T20:01:00Z"
    paths["state"].write_text(json.dumps(state))
    schema=json.loads(paths["schema"].read_text());schema["last_date"]="2009-09-08"
    paths["schema"].write_text(json.dumps(schema))
    golden=json.loads(paths["golden"].read_text())
    golden["transitions"][-1][0]="2009-09-08"
    golden["transition_sha256"]=transition_hash(golden["transitions"])
    paths["golden"].write_text(json.dumps(golden))
    assert check(paths)["status"]=="VALID"
    # Shift a stable 3x day from Sept 3 to Sept 4. Counts, transition SHA,
    # sorted/unique dates and boundaries all still pass. Full daily SHA must fail.
    data[1][0]="2009-09-04"
    write(data)
    result=check(paths)
    assert result["checks"]["frozen_transition_identity"] is True
    assert result["checks"]["frozen_daily_leverage_distribution"] is True
    assert "FROZEN_DAILY_STATE_SHA_DRIFT" in result["errors"]
    assert "FROZEN_SESSION_CALENDAR_SHA_DRIFT" in result["errors"]


def test_original_chart_extractor_and_rejection_of_fake_original(tmp_path):
    paths,_,_=fixture(tmp_path)
    ts=[int(datetime.fromisoformat(day+"T20:01:00+00:00").timestamp())
        for day in ["2009-09-01","2009-09-02","2009-09-03"]]
    chart={"charts":{"SL724":{"series":{
      "Leverage":{"values":list(zip(ts,[3,3,2]))},
      "NAV":{"values":list(zip(ts,[.97,1.01,1.10]))},
      "Drawdown":{"values":list(zip(ts,[-3,0,0]))},
    }}}}
    p=tmp_path/"original.json";p.write_text(json.dumps(chart))
    rows,audit=extract(p,expected_source_sha=None,manifest=paths["state"],golden=paths["golden"])
    assert len(rows)==3 and audit["transition_count"]==2
    assert audit["same_input_parity_proven"] is False
    assert not audit["contains_daily_indicators"]
    compare=compare_original_vs_execution_proxy(rows,{"daily":[
        {"date":"2009-09-01","l":3,"signal":"2009-08-31"},
        {"date":"2009-09-02","l":2,"signal":"2009-09-01"}]})
    assert compare["overlap_sessions"]==2
    assert compare["matching_exposures"]==1
    assert not compare["same_input_parity_proven"]
    try:
        extract(p,expected_source_sha="bad",manifest=paths["state"],golden=paths["golden"])
        raise AssertionError("must reject invalid original")
    except ValueError as exc:
        assert "SOURCE_SHA256_MISMATCH" in str(exc)


def test_missing_input_is_blocked(tmp_path):
    r=compare(path=tmp_path/"absent.csv",out=tmp_path/"out.json")
    assert r["status"]=="BLOCKED_MISSING_IDENTICAL_INPUT_EXPORT"
    assert not r["same_input_parity_proven"]


def test_dossier_does_not_promote_spoofed_matching_state(tmp_path, monkeypatch):
    from qc_parity_dossier import build
    monkeypatch.chdir(tmp_path)
    (tmp_path/"governance").mkdir()
    (tmp_path/"shadow_history").mkdir()
    (tmp_path/"governance/qc_724_daily_state_manifest.json").write_text(
        json.dumps({"sessions":3774,"full_state_sha256":"golden"}))
    (tmp_path/"shadow_history/qc_input_ingestion.json").write_text(
        json.dumps({"status":"VALID","rows":3774,
                    "source_authenticity_proven":False}))
    (tmp_path/"shadow_history/qc_same_input_parity.json").write_text(
        json.dumps({"same_input_state_match":True,"compared_sessions":3774,
                    "mismatch_count":0,"same_input_parity_proven":True,
                    "input_validation":{"status":"VALID"}}))
    report=build()
    assert report["status"]=="REFERENCE_PARITY_ONLY"
    assert report["same_input_evidence"]["mathematical_state_match"] is True
    assert report["same_input_evidence"]["proven"] is False
    assert any("authenticity" in x.lower() for x in report["blockers"])


def test_pinned_67_original_transition_sha_uses_numeric_float_canonicalization():
    # Immutable golden SHA was produced with 3.0/2.0/0.0 as floating-point
    # leverage values, even though the checked-in JSON prints them as 3/2/0.
    # Before this regression, EVERY genuine original LEAN audit would fail.
    golden=json.loads(Path("governance/qc_724_leverage_transitions.json").read_text())
    original=golden["transitions"]
    assert len(original)==67
    assert transition_hash(original)==golden["transition_sha256"]
    assert transition_hash([[day,float(lev)] for day,lev in original])==golden["transition_sha256"]
    altered=[list(row) for row in original]
    altered[7][0]="2010-08-12"
    assert transition_hash(altered)!=golden["transition_sha256"]

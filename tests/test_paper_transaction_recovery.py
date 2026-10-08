"""Crash injection for the forward-only local paper transaction coordinator."""
import csv
import json

import pytest
import paper_transaction as tx

def paths(tmp_path):
    base=tmp_path/"paper"
    return {k:base/f for k,f in (("trades","trades.csv"),("ledger","ledger.csv"),
                                 ("state","state.json"),("latest","latest.md"))}

def record(day="2026-10-08"):
    return {"session_date":day,"signal_date":"2026-10-07","equity":100123.,
            "drawdown":-.01,"paper_action":"RECONCILE_ACTUAL_HOLDINGS",
            "target_tracking_gap_after":.003}

def trade():
    return {"execution_session":"2026-10-08","symbol":"TQQQ","side":"BUY","qty":14}

def state():
    return {"cash":200.,"shares":{"QQQ":0,"TQQQ":14},
            "last_mark_session":"2026-10-08"}

def load_csv(path):
    with path.open(newline="",encoding="utf-8") as handle:
        return list(csv.DictReader(handle))

def test_completed_session_persists_all_four_artifacts_once(tmp_path):
    p=paths(tmp_path)
    result=tx.commit(p,record(),[trade()],state(),"paper marked")
    assert result["trades"]==1 and result["session_date"]=="2026-10-08"
    assert load_csv(p["ledger"])[0]["session_date"]=="2026-10-08"
    assert load_csv(p["trades"])[0]["qty"]=="14"
    assert json.loads(p["state"].read_text())["last_mark_session"]=="2026-10-08"
    assert p["latest"].read_text()=="paper marked"
    assert tx.recover(p) is None
    assert list((p["state"].parent/".transactions").glob("*.json"))==[]

def test_ledger_crash_recovers_exact_prepare_not_recomputed_fills(tmp_path,monkeypatch):
    p=paths(tmp_path)
    actual=tx.atomic_replace
    attempts={"fail":True}
    def crash(path,content):
        if path==p["ledger"] and attempts["fail"]:
            attempts["fail"]=False
            raise OSError("INJECTED_LEDGER_WRITE_FAILURE")
        return actual(path,content)
    monkeypatch.setattr(tx,"atomic_replace",crash)
    with pytest.raises(OSError,match="INJECTED"):
        tx.commit(p,record(),[trade()],state(),"paper marked")
    assert p["trades"].exists()
    assert not p["ledger"].exists()
    pending=list((p["state"].parent/".transactions").glob("*.json"))
    assert len(pending)==1
    assert tx.recover(p)["trades"]==1
    assert len(load_csv(p["ledger"]))==1
    assert len(load_csv(p["trades"]))==1
    assert tx.recover(p) is None

def test_crash_after_all_outputs_before_manifest_unlink_is_idempotent(tmp_path,monkeypatch):
    p=paths(tmp_path)
    original=tx.Path.unlink
    fired={"v":False}
    def fail_unlink(path,*args,**kwargs):
        if path.name.endswith(".json") and path.parent.name==".transactions" and not fired["v"]:
            fired["v"]=True
            raise OSError("INJECTED_FINAL_ACK_FAILURE")
        return original(path,*args,**kwargs)
    monkeypatch.setattr(tx.Path,"unlink",fail_unlink)
    with pytest.raises(OSError,match="INJECTED_FINAL_ACK_FAILURE"):
        tx.commit(p,record(),[trade()],state(),"paper marked")
    assert tx.recover(p)["session_date"]=="2026-10-08"
    assert len(load_csv(p["ledger"]))==1
    assert len(load_csv(p["trades"]))==1

def test_external_ledger_tamper_during_recovery_fails_closed(tmp_path,monkeypatch):
    p=paths(tmp_path)
    original=tx.atomic_replace
    def fail(path,content):
        if path==p["state"]:
            raise OSError("INTERRUPTED_AFTER_LEDGER")
        return original(path,content)
    monkeypatch.setattr(tx,"atomic_replace",fail)
    with pytest.raises(OSError):
        tx.commit(p,record(),[trade()],state(),"paper marked")
    p["ledger"].write_text("session_date\\n2020-01-01\\n")
    with pytest.raises(tx.PaperTransactionError,match="EXTERNAL_PAPER_DRIFT:ledger"):
        tx.recover(p)

def test_extends_existing_csv_schema_without_losing_prior_rows(tmp_path):
    p=paths(tmp_path)
    p["ledger"].parent.mkdir(parents=True)
    p["ledger"].write_text("session_date,equity,drawdown\\n2026-10-07,100000,0\\n".replace("\\n","\n"))
    tx.commit(p,record(),[],state(),"paper")
    data=load_csv(p["ledger"])
    assert len(data)==2
    assert data[0]["equity"]=="100000"
    assert data[0]["target_tracking_gap_after"]==""
    assert data[1]["target_tracking_gap_after"]=="0.003"
    assert not p["trades"].exists()

def test_corrupted_prepare_is_not_silently_replayed(tmp_path,monkeypatch):
    p=paths(tmp_path)
    original=tx.atomic_replace
    def fail(path,content):
        if path==p["ledger"]: raise OSError("INJECTED")
        return original(path,content)
    monkeypatch.setattr(tx,"atomic_replace",fail)
    with pytest.raises(OSError):
        tx.commit(p,record(),[trade()],state(),"paper")
    pending=next((p["state"].parent/".transactions").glob("*.json"))
    payload=json.loads(pending.read_text())
    payload["equity"]=999
    pending.write_text(json.dumps(payload))
    with pytest.raises(tx.PaperTransactionError,match="CORRUPT_PAPER_PREPARE_RECORD"):
        tx.recover(p)

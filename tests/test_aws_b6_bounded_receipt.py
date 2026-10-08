"""B6: bounded, crash-atomic paper receipt for the AWS evidence Lambda."""
import json

import pytest
import paper_transaction as tx

def _paths(root):
    return {key: root/name for key,name in (
        ("trades","trades.csv"),("ledger","ledger.csv"),
        ("state","state.json"),("latest","latest.md"),
        ("snapshot","latest_session.json"))}

def _row():
    return {"session_date":"2026-10-08","signal_date":"2026-10-07",
            "equity":1000.0,"drawdown":0.0,"trade_count_session":1,
            "execution_source":"YFINANCE_1M_RAW"}

def _trade():
    return {"execution_session":"2026-10-08","symbol":"TQQQ",
            "side":"BUY","qty":1,"signal_date":"2026-10-07"}

def test_bounded_receipt_is_written_in_same_transaction(tmp_path):
    p=_paths(tmp_path)
    tx.commit(p,_row(),[_trade()],{"cash":0},"paper")
    receipt=json.loads(p["snapshot"].read_text())
    assert receipt=={"schema_version":1,"session_date":"2026-10-08",
                     "broker_fills_observed":False,"row":_row(),"trades":[_trade()]}
    assert tx.recover(p) is None

def test_receipt_crash_restarts_with_exact_prepared_bytes(tmp_path,monkeypatch):
    p=_paths(tmp_path)
    original=tx.atomic_replace
    fired={"value":False}
    def crash(path,content):
        if path==p["snapshot"] and not fired["value"]:
            fired["value"]=True
            raise OSError("CRASH_BEFORE_RECEIPT")
        return original(path,content)
    monkeypatch.setattr(tx,"atomic_replace",crash)
    with pytest.raises(OSError,match="CRASH_BEFORE_RECEIPT"):
        tx.commit(p,_row(),[_trade()],{"cash":0},"paper")
    assert not p["snapshot"].exists()
    recovered=tx.recover(p)
    assert recovered["session_date"]=="2026-10-08"
    assert json.loads(p["snapshot"].read_text())["trades"]==[_trade()]
    assert tx.recover(p) is None

def test_external_receipt_tamper_fails_closed(tmp_path,monkeypatch):
    p=_paths(tmp_path)
    original=tx.atomic_replace
    def crash(path,content):
        if path==p["snapshot"]: raise OSError("INTERRUPTED")
        return original(path,content)
    monkeypatch.setattr(tx,"atomic_replace",crash)
    with pytest.raises(OSError,match="INTERRUPTED"):
        tx.commit(p,_row(),[_trade()],{"cash":0},"paper")
    p["snapshot"].write_text('{"evil":true}')
    with pytest.raises(tx.PaperTransactionError,match="EXTERNAL_PAPER_DRIFT:snapshot"):
        tx.recover(p)

def test_missing_receipt_destination_blocks_recovery(tmp_path,monkeypatch):
    p=_paths(tmp_path)
    original=tx.atomic_replace
    def crash(path,content):
        if path==p["snapshot"]: raise OSError("INTERRUPTED")
        return original(path,content)
    monkeypatch.setattr(tx,"atomic_replace",crash)
    with pytest.raises(OSError):
        tx.commit(p,_row(),[],{"cash":0},"paper")
    p.pop("snapshot")
    with pytest.raises(tx.PaperTransactionError,match="MISSING_PREPARED_DESTINATION:snapshot"):
        tx.recover(p)

def test_aws_handler_reads_bounded_receipt_not_accumulating_csv():
    from pathlib import Path
    code=Path("infra/aws/paper-evidence-handler.py").read_text()
    assert 'read("paper_portfolio/latest_session.json")' in code
    assert 'read("paper_portfolio/lg.csv")' not in code
    assert 'read("paper_portfolio/trs.csv")' not in code
    assert 'INVALID_SESSION_RECEIPT' in code
    assert 'BAD_TRADE_WINDOW' in code
    assert 'DIVERGENT_PAPER_DUPLICATE' in code

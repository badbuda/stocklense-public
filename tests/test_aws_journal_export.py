"""Regression tests for DynamoDB CSV export without AWS credentials."""
import csv
import hashlib
import json

import pytest

from aws_journal_export import (
    FIRST_FORWARD_DATE, FIELDS, TRADE_FIELDS, decode_paper, decode_signal,
    exchange_sessions, export, inspect_session,
)

DAY="2026-10-08"


def ddb(text, field):
    return {"S":text}


def good_items():
    signal={"mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
            "action":"NO_CHANGE",
            "latest":{"asof_date":DAY,"level":3,"target_leverage":3.0,
                      "defense_active":False,"qqq_weight":0,"tqqq_weight":.985}}
    signal_raw=json.dumps(signal)
    sig={"signal_json":ddb(signal_raw,"S"),
         "signal_sha256":ddb(hashlib.sha256(signal_raw.encode()).hexdigest(),"S"),
         "broker_orders_authorized":{"BOOL":False},
         "recorded_at_utc":ddb("2026-10-09T09:10:30+00:00","S")}
    paper={
        "row":{"session_date":DAY,"execution_source":"YFINANCE_1M_RAW",
               "equity":97427.96316,"cumulative_return":-.02572036839,
               "drawdown":-.02572036839,"cash":1404.62,"qqq_shares":0,
               "tqqq_shares":1197,"trade_count_session":1,
               "paper_action":"BOOTSTRAP_TO_TARGET","cumulative_fees":19.715,
               "cumulative_slippage_cost":98.47},
        "trs":[{"execution_session":DAY,"signal_date":"2026-10-07",
                "symbol":"TQQQ","side":"BUY","qty":1197,
                "time_et":"09:32","modeled_fill_price":82.35}],
    }
    raw=json.dumps(paper,sort_keys=True,separators=(",",":"))
    receipt={"paper_evidence_json":ddb(raw,"S"),
             "paper_sha256":ddb(hashlib.sha256(raw.encode()).hexdigest(),"S"),
             "broker_orders_authorized":{"BOOL":False},
             "broker_fills_observed":{"BOOL":False}}
    return sig,receipt


def test_export_contains_joined_signal_paper_and_one_trade():
    signal,paper=good_items()
    row,trades=inspect_session(DAY,signal,paper)
    assert set(row)==set(FIELDS)
    assert row["status"]=="PASS" and row["signal_level"]==3
    assert row["signal_tqqq_weight_pct"]==98.5
    assert row["paper_cumulative_return_pct"] == pytest.approx(-2.572036839)
    assert row["paper_equity_usd"]==pytest.approx(97427.96316)
    assert row["paper_trade_count"]==1
    assert set(trades[0])==set(TRADE_FIELDS)
    assert trades[0]["symbol"]=="TQQQ"


@pytest.mark.parametrize("signal,paper,status",[
    (False,False,"MISSING_BOTH"),(False,True,"MISSING_SIGNAL"),
    (True,False,"MISSING_PAPER"),
])
def test_missing_sessions_are_explicit_not_synthesized(signal,paper,status):
    sig,item=good_items()
    row,trades=inspect_session(DAY,sig if signal else None,item if paper else None)
    assert row["status"]==status
    assert (len(trades)==1)==paper


def test_signal_tampering_fails_closed():
    sig,_=good_items()
    sig["signal_sha256"]["S"]="0"*64
    with pytest.raises(ValueError,match="SIGNAL_SHA256_MISMATCH"):
        decode_signal(sig,DAY)


def test_paper_tampering_fails_closed():
    _,paper=good_items()
    paper["paper_sha256"]["S"]="0"*64
    with pytest.raises(ValueError,match="PAPER_SHA256_MISMATCH"):
        decode_paper(paper,DAY)


def test_broker_flags_cannot_be_claimed():
    sig,paper=good_items()
    sig["broker_orders_authorized"]["BOOL"]=True
    with pytest.raises(ValueError,match="UNSAFE_SIGNAL_BROKER_FLAG"):
        inspect_session(DAY,sig,paper)
    sig,paper=good_items()
    paper["broker_fills_observed"]["BOOL"]=True
    with pytest.raises(ValueError,match="FALSE_OBSERVED_BROKER_FILLS"):
        inspect_session(DAY,sig,paper)


def test_wrong_trades_key_is_rejected():
    _,paper=good_items()
    obj=json.loads(paper["paper_evidence_json"]["S"])
    obj["trades"]=obj.pop("trs")
    raw=json.dumps(obj)
    paper["paper_evidence_json"]["S"]=raw
    paper["paper_sha256"]["S"]=hashlib.sha256(raw.encode()).hexdigest()
    with pytest.raises(ValueError,match="INVALID_PAPER_TRADE_COUNT"):
        decode_paper(paper,DAY)


def test_export_writes_csv_json_and_preserves_missing(tmp_path):
    sig,paper=good_items()
    def fetch(table,key):
        assert table=="test-table"
        return {DAY:sig,DAY+"#PAPER":paper}.get(key)
    result=export("test-table",tmp_path,[DAY,"2026-10-09"],fetch=fetch)
    assert result["statuses"]["PASS"]==1
    assert result["statuses"]["MISSING_BOTH"]==1
    assert result["all_sessions_pass"] is False
    with (tmp_path/"sessions.csv").open(encoding="utf-8-sig",newline="") as f:
        rows=list(csv.DictReader(f))
    assert len(rows)==2
    assert rows[1]["status"]=="MISSING_BOTH"
    assert rows[0]["paper_equity_usd"]=="97427.96316"
    assert len(list(csv.DictReader((tmp_path/"trades.csv").open(encoding="utf-8-sig",newline=""))))==1
    assert json.loads((tmp_path/"summary.json").read_text())["broker_fills_observed"] is False


def test_export_invalid_record_never_claims_pass(tmp_path):
    sig,paper=good_items()
    paper["paper_sha256"]["S"]="0"*64
    def fetch(table,key):
        return {DAY:sig,DAY+"#PAPER":paper}.get(key)
    result=export("test-table",tmp_path,[DAY],fetch=fetch)
    assert result["statuses"]["INVALID_EVIDENCE"]==1
    assert result["errors"]


def test_exchange_calendar_excludes_weekends():
    sessions=exchange_sessions(FIRST_FORWARD_DATE,"2026-10-12",10)
    assert sessions==["2026-10-08","2026-10-09","2026-10-12"]

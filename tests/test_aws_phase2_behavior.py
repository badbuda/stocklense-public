"""Pure behavioral AWS paper-evidence gate tests: no AWS, broker or Yahoo calls."""
from datetime import datetime,timezone
from pathlib import Path

SRC=Path("infra/aws/paper-evidence-handler.py").read_text()
CODE=SRC.replace("import boto3,hashlib,json,os,urllib.request",
                 "import hashlib,json,os,urllib.request")
CODE=CODE.replace("from botocore.exceptions import ClientError","")
ns={}
exec(compile(CODE,"paper-evidence-handler.py","exec"),ns)
check=ns["evidence"]

DAY="2026-10-08"
SIGNAL="2026-10-07"
NOW=datetime(2026,10,9,9,21,tzinfo=timezone.utc)

def inputs():
    report={"status":"PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS",
            "latest_session":DAY,"broker_fills_observed":False,
            "verified_paper_sessions":1}
    row={"session_date":DAY,"signal_date":SIGNAL,"execution_source":"YFINANCE_1M_RAW",
         "target_qqq_weight":"0","target_tqqq_weight":"0.985",
         "trade_count_session":"1"}
    trade={"execution_session":DAY,"signal_date":SIGNAL,
           "symbol":"TQQQ","side":"BUY","time_et":"09:32"}
    snap={"schema_version":1,"session_date":DAY,"broker_fills_observed":False,
          "row":row,"trades":[trade]}
    prior={"generated_at_utc":"2026-10-08T09:29:00+00:00",
           "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
           "latest":{"asof_date":SIGNAL,"qqq_weight":0.0,"tqqq_weight":.985}}
    current={"mode":"SHADOW_ONLY_NO_BROKER_ACTIONS","latest":{"asof_date":DAY}}
    return [report,snap,prior,current]

def rejects(values,part):
    try: check(NOW,*values)
    except RuntimeError as exc:
        assert part in str(exc),exc
    else: raise AssertionError("Invalid evidence accepted")

def test_valid_observed_paper_evidence_is_model_only():
    day,row,trades=check(NOW,*inputs())
    assert day==DAY and row["execution_source"]=="YFINANCE_1M_RAW"
    assert len(trades)==1

def test_cannot_archive_unfinished_session():
    values=inputs()
    try: check(datetime(2026,10,9,6,0,tzinfo=timezone.utc),*values)
    except RuntimeError as exc: assert str(exc)=="NOT_CLOSED"
    else: raise AssertionError("Captured incomplete market session")

def test_audit_must_be_real_pass():
    values=inputs();values[0]["status"]="WAITING_FOR_PROSPECTIVE_PAPER"
    rejects(values,"AUDIT_NOT_PASS")

def test_no_synthetic_tqqq_source():
    values=inputs();values[1]["row"]["execution_source"]="QQQ_TIMES_3"
    rejects(values,"SYNTHETIC_SOURCE")

def test_prior_signal_must_precede_open():
    values=inputs();values[2]["generated_at_utc"]="2026-10-08T14:00:00+00:00"
    rejects(values,"LATE_SIGNAL")

def test_no_missing_trade_receipts():
    values=inputs();values[1]["row"]["trade_count_session"]="2"
    rejects(values,"TRADE_COUNT_BAD")

def test_no_stale_current_signal():
    values=inputs();values[3]["latest"]["asof_date"]="2026-10-07"
    rejects(values,"NO_LATEST_SIGNAL")

def test_no_target_mismatch():
    values=inputs();values[2]["latest"]["tqqq_weight"]=0.5
    rejects(values,"WRONG_TARGET")

def test_no_future_session_receipt():
    values=inputs();values[1]["session_date"]="2026-10-09"
    rejects(values,"INVALID_SESSION_RECEIPT")

def test_no_broker_fill_claim():
    values=inputs();values[1]["broker_fills_observed"]=True
    rejects(values,"INVALID_SESSION_RECEIPT")

def test_receipt_trade_window_is_tied_to_session():
    values=inputs();values[1]["trades"][0]["execution_session"]="2026-10-07"
    rejects(values,"BAD_TRADE_WINDOW")

def test_previous_ny_session_is_required_even_after_midnight():
    values=inputs();values[1]["session_date"]="2026-10-09"
    rejects(values,"INVALID_SESSION_RECEIPT")

def test_not_closed_if_invoked_before_four_ny():
    values=inputs()
    try: check(datetime(2026,10,9,7,0,tzinfo=timezone.utc),*values)
    except RuntimeError as exc: assert str(exc)=="NOT_CLOSED"
    else: raise AssertionError("Premature AWS paper archive accepted")

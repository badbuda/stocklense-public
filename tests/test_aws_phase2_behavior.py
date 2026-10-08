"""Behavioral tests of the pure AWS paper-evidence gate; no AWS or Yahoo calls."""
import csv
import io
from datetime import datetime,timezone
from pathlib import Path

SRC=Path("infra/aws/paper-evidence-handler.py").read_text()
CODE=SRC.replace("import boto3,csv,hashlib,io,json,os,urllib.request",
                 "import csv,hashlib,io,json,os,urllib.request")
CODE=CODE.replace("from botocore.exceptions import ClientError","")
ns={}
exec(compile(CODE,"paper-evidence-handler.py","exec"),ns)
check=ns["evidence"]

DAY="2026-10-08"
SIGNAL="2026-10-07"
NOW=datetime(2026,10,9,3,21,tzinfo=timezone.utc)

def csv_table(rows):
    f=io.StringIO()
    w=csv.DictWriter(f,fieldnames=list(rows[0]))
    w.writeheader()
    w.writerows(rows)
    return f.getvalue()

def inputs():
    report={"status":"PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS",
            "latest_session":DAY,"broker_fills_observed":False,
            "verified_paper_sessions":1}
    row={"session_date":DAY,"signal_date":SIGNAL,"execution_source":"YFINANCE_1M_RAW",
         "target_qqq_weight":"0","target_tqqq_weight":"0.985",
         "trade_count_session":"1"}
    trade={"execution_session":DAY,"signal_date":SIGNAL,
           "symbol":"TQQQ","side":"BUY","time_et":"09:32"}
    prior={"generated_at_utc":"2026-10-08T09:29:00+00:00",
           "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
           "latest":{"asof_date":SIGNAL,"qqq_weight":0.0,"tqqq_weight":.985}}
    current={"mode":"SHADOW_ONLY_NO_BROKER_ACTIONS","latest":{"asof_date":DAY}}
    return [report,csv_table([row]),csv_table([trade]),prior,current]

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
    try: check(datetime(2026,10,8,19,0,tzinfo=timezone.utc),*values)
    except RuntimeError as exc: assert str(exc)=="NOT_CLOSED"
    else: raise AssertionError("Captured incomplete market session")

def test_audit_must_be_real_pass():
    values=inputs();values[0]["status"]="WAITING_FOR_PROSPECTIVE_PAPER"
    rejects(values,"AUDIT_NOT_PASS")

def test_no_synthetic_tqqq_source():
    values=inputs();values[1]=values[1].replace("YFINANCE_1M_RAW","QQQ_TIMES_3")
    rejects(values,"SYNTHETIC_SOURCE")

def test_prior_signal_must_precede_open():
    values=inputs();values[3]["generated_at_utc"]="2026-10-08T14:00:00+00:00"
    rejects(values,"LATE_SIGNAL")

def test_no_missing_trade_receipts():
    values=inputs()
    lines=values[1].splitlines()
    cols=lines[0].split(",")
    fields=lines[1].split(",")
    fields[cols.index("trade_count_session")]="2"
    values[1]=",".join(cols)+"\n"+",".join(fields)+"\n"
    rejects(values,"TRADE_COUNT_BAD")

def test_no_stale_current_signal():
    values=inputs();values[4]["latest"]["asof_date"]="2026-10-07"
    rejects(values,"NO_LATEST_SIGNAL")

def test_no_target_mismatch():
    values=inputs();values[3]["latest"]["tqqq_weight"]=0.5
    rejects(values,"WRONG_TARGET")

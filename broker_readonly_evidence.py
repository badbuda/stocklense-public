"""Excellence/manual broker snapshot reconciliation; strictly READ ONLY.

No Excellence API contract is assumed; no account login, passwords, exports,
network, broker order submission or production order permissions.
Only manually normalized CSV columns Symbol,Quantity. Paper modeled positions
are NOT a real brokerage account.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from datetime import datetime, timedelta, timezone
import csv
import hashlib
import io
import json
import re
from pathlib import Path

SYMBOL=re.compile(r"^[A-Z][A-Z0-9.-]{0,19}$")
MAX_POSITIONS=500

def positions_csv(raw: bytes, *, name: str) -> dict[str,Decimal]:
    if len(raw)>100_000 or b"\x00" in raw:
        raise ValueError(name+"_INVALID_INPUT_SIZE")
    try:
        reader=csv.DictReader(io.StringIO(raw.decode("utf-8-sig"),newline=""))
        if reader.fieldnames != ["Symbol","Quantity"]:
            raise ValueError(name+"_REQUIRES_SYMBOL_QUANTITY_EXACT_HEADERS")
        data={}
        for row in reader:
            sym=row["Symbol"]
            if not isinstance(sym,str) or not SYMBOL.fullmatch(sym) or sym in data:
                raise ValueError(name+"_DUPLICATE_OR_INVALID_SYMBOL")
            try:
                qty=Decimal(row["Quantity"])
            except (InvalidOperation,TypeError) as exc:
                raise ValueError(name+"_INVALID_QUANTITY") from exc
            if not qty.is_finite() or qty<0 or qty>Decimal('1000000000') or qty.as_tuple().exponent < -8:
                raise ValueError(name+"_INVALID_QUANTITY")
            data[sym]=qty
            if len(data)>MAX_POSITIONS:
                raise ValueError(name+"_TOO_MANY_POSITIONS")
    except (UnicodeError,csv.Error,KeyError) as exc:
        raise ValueError(name+"_INVALID_CSV") from exc
    if not data:
        raise ValueError(name+"_EMPTY_POSITIONS")
    return data

def reconcile_readonly(*, intended_csv:bytes, observed_csv:bytes,
                       snapshot_at_utc:datetime, now:datetime,
                       broker_label:str="EXCELLENCE_USER_SUPPLIED_EXPORT")->dict:
    if broker_label!="EXCELLENCE_USER_SUPPLIED_EXPORT":
        raise ValueError("UNVERIFIED_BROKER_FORMAT")
    if now.tzinfo is None or snapshot_at_utc.tzinfo is None:
        raise ValueError("BROKER_SNAPSHOT_NAIVE_CLOCK")
    current=now.astimezone(timezone.utc)
    when=snapshot_at_utc.astimezone(timezone.utc)
    if when>current or current-when>timedelta(hours=48):
        raise ValueError("BROKER_SNAPSHOT_STALE_OR_FUTURE")
    want=positions_csv(intended_csv,name="INTENDED")
    have=positions_csv(observed_csv,name="OBSERVED")
    discrepancies=[
        {"symbol":symbol,"intended_qty":str(want.get(symbol,Decimal(0))),
         "observed_qty":str(have.get(symbol,Decimal(0))),
         "delta_qty":str(have.get(symbol,Decimal(0))-want.get(symbol,Decimal(0)))}
        for symbol in sorted(set(want)|set(have))
        if want.get(symbol,Decimal(0))!=have.get(symbol,Decimal(0))
    ]
    return {
        "status":"MATCH_READ_ONLY_NOT_TRADE_AUTHORIZATION" if not discrepancies
                 else "MISMATCH_READ_ONLY_NO_TRADE",
        "broker_data_origin":broker_label,
        "observed_asof_utc":when.isoformat(),
        "intended_file_sha256":hashlib.sha256(intended_csv).hexdigest(),
        "observed_file_sha256":hashlib.sha256(observed_csv).hexdigest(),
        "symbol_count":len(set(want)|set(have)),
        "differences":discrepancies,
        "csv_input_is_self_reported_not_authenticated_broker":True,
        "api_account_ownership_proven":False,
        "funds_available_proven":False,
        "settlement_and_orders_reconciled":False,
        "broker_order_approval":False,
        "live_gate_eligible":False,
        "broker_actions":False,
    }

def main():
    import argparse
    parser=argparse.ArgumentParser(description="Offline, no-API read-only reconciliation")
    parser.add_argument("--intended",type=Path,required=True)
    parser.add_argument("--observed",type=Path,required=True)
    parser.add_argument("--snapshot-at-utc",required=True)
    opts=parser.parse_args()
    report=reconcile_readonly(
        intended_csv=opts.intended.read_bytes(),
        observed_csv=opts.observed.read_bytes(),
        snapshot_at_utc=datetime.fromisoformat(opts.snapshot_at_utc.replace("Z","+00:00")),
        now=datetime.now(timezone.utc),
    )
    print(json.dumps(report,indent=2,ensure_ascii=False))
    if report["differences"]:
        raise SystemExit(2)

if __name__=="__main__":
    main()

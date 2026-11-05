"""SL-50: analyze an exported immutable ST Paper receipt with supplied FX evidence.

Usage: python research/paper_tax_receipts.py --receipt paper.json
       --sha256 <verified-s3-receipt-sha256> --fx dated_fx.json --out tax.json
No AWS mutations, orders, network requests or modification of baseline records.
"""
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from stocklens.tax_research import TaxBook


def examine(raw: bytes, expected_sha: str, fx: dict, tax_rate="0.25") -> dict:
    digest = hashlib.sha256(raw).hexdigest()
    if len(expected_sha)!=64 or digest != expected_sha:
        raise ValueError("UNVERIFIED_S3_RECEIPT_SHA")
    receipt = json.loads(raw)
    if receipt.get("broker_fills_observed") is not False or receipt.get("broker_orders_authorized") is not False:
        raise ValueError("NOT_SAFE_MODELED_RECEIPT")
    ledger = receipt["history"]["ledger"]
    history = receipt["history"]["trades"]
    if not ledger or ledger[-1]["session_date"] != receipt["session"]:
        raise ValueError("MISSING_OR_INCONSISTENT_SESSION_HISTORY")
    if receipt["row"]["session_date"] != receipt["session"]:
        raise ValueError("MISMATCHED_DAILY_ROW")
    if sum(int(d["trade_count_session"]) for d in ledger) != len(history):
        raise ValueError("HISTORY_TRADE_COUNT_MISMATCH")
    book = TaxBook(rate=tax_rate)
    for t in sorted(history,key=lambda t:(t["execution_session"],t["time_et"])):
        day=t["execution_session"]
        if day not in fx:
            raise ValueError("MISSING_BROKER_FX_FOR_TRADE:"+day)
        kwargs=(day,t["symbol"],int(t["qty"]),t["modeled_fill_price"],t["fee"],fx[day])
        if t["side"]=="BUY":
            book.buy(*kwargs)
        elif t["side"]=="SELL":
            book.sell(*kwargs)
        else:
            raise ValueError("UNKNOWN_TRADE_SIDE")
    row=receipt["row"]
    for s in ("QQQ","TQQQ"):
        if book.quantity(s) != int(row[s.lower()+"_shares"]):
            raise ValueError("TAX_LOT_QTY_DIFFERS_FROM_PAPER:"+s)
    day=receipt["session"]
    assessed=Decimal(book.summary()["tax_assessed_ils"])
    if assessed and day not in fx:
        raise ValueError("MISSING_FX_FOR_NET_NAV:"+day)
    gross=Decimal(str(row["equity"]))
    # Hypothetical immediate withdrawal accumulated in today's USD equivalents;
    # cannot replace real withholding cashflows or reproduce tax-funded orders.
    hypothetical_net=gross-assessed/Decimal(str(fx[day])) if assessed else gross
    return {"status":"RESEARCH_ONLY_TAX_RECEIPT_REPLAY",
            "session":day,"sha256":digest,"trades_in_full_history":len(history),
            "gross_paper_nav_usd":str(gross),
            "hypothetical_after_tax_value_usd":str(hypothetical_net),
            "basis":"PRETAX_ST_PAPER_PLUS_HYPOTHETICAL_TAX_NO_BROKER_WITHHOLDING",
            "tax":book.summary(),"tax_events":book.events}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--receipt",required=True)
    p.add_argument("--sha256",required=True)
    p.add_argument("--fx",required=True,help="JSON map date -> ILS per USD (verified rates)")
    p.add_argument("--out",required=True)
    args=p.parse_args()
    report=examine(Path(args.receipt).read_bytes(),args.sha256,
                   json.loads(Path(args.fx).read_text()))
    Path(args.out).write_text(json.dumps(report,indent=2)+"\n")
    print(report["status"],report["gross_paper_nav_usd"],report["hypothetical_after_tax_value_usd"])


if __name__=="__main__":
    main()

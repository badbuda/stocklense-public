"""Create a private, authenticated tax-dashboard receipt from observed ST Paper.

Research only. Never write to docs/ or submit broker/AWS orders.
FX evidence must be independently verified by an operator; this program
checks the attestation's exact JSON fingerprint, not provider authenticity.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from decimal import Decimal
from pathlib import Path

from research.paper_tax_receipts import examine
from stocklens.tax_research import TaxBook


def _d(x):
    d = Decimal(str(x))
    if not d.is_finite():
        raise ValueError("NONFINITE_TAX_REPORT_VALUE")
    return d


def _fx_hash(fx):
    return hashlib.sha256(json.dumps(fx, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def build(raw: bytes, receipt_sha: str, fx: dict, attestation: dict):
    if (attestation.get("manually_verified") is not True or
        attestation.get("fx_data_sha256") != _fx_hash(fx) or
        not str(attestation.get("independent_source", "")).strip() or
        not str(attestation.get("verified_by", "")).strip()):
        raise ValueError("NO_INDEPENDENT_FX_ATTESTATION")
    prior = examine(raw, receipt_sha, fx)
    receipt = json.loads(raw)
    row = receipt["row"]
    day = receipt["session"]
    if day not in fx or _d(fx[day]) <= 0:
        raise ValueError("MISSING_TERMINAL_FX")
    fx_today = _d(fx[day])
    cash = _d(row["cash"])
    if cash < 0:
        raise ValueError("NEGATIVE_PAPER_CASH")
    book = TaxBook(rate="0.25")
    for t in sorted(receipt["history"]["trades"], key=lambda x: (x["execution_session"],x["time_et"])):
        trade_day=t["execution_session"]
        params=(trade_day,t["symbol"],int(t["qty"]),t["modeled_fill_price"],t["fee"],fx[trade_day])
        if t["side"] == "BUY":
            book.buy(*params)
        elif t["side"] == "SELL":
            book.sell(*params)
        else:
            raise ValueError("INVALID_PAPER_SIDE")
    pre_tax=book.tax_assessed_ils
    if str(pre_tax) != str(_d(prior["tax"]["tax_assessed_ils"])):
        raise ValueError("REALIZED_TAX_REPLAY_MISMATCH")
    fee_bps=_d(row["fee_bps"])
    slip_bps=_d(row["slippage_bps"])
    if fee_bps < 0 or fee_bps > 100 or slip_bps < 0 or slip_bps > 500:
        raise ValueError("INVALID_FEE_SLIPPAGE_ASSUMPTIONS")
    nominal_cash_on_exit=cash
    shares_value=cash
    for symbol in ("QQQ","TQQQ"):
        qty=int(row[symbol.lower()+"_shares"])
        close=_d(row[symbol.lower()+"_close"])
        if qty < 0 or close <= 0 or book.quantity(symbol)!=qty:
            raise ValueError("TAX_LOT_AND_PAPER_POSITION_MISMATCH")
        shares_value+=qty*close
        if not qty:
            continue
        fill=close*(1-slip_bps/Decimal(10000))
        fee=qty*fill*fee_bps/Decimal(10000)
        book.sell(day,symbol,qty,fill,fee,fx_today)
        nominal_cash_on_exit+=qty*fill-fee
    gross=_d(row["equity"])
    if abs(shares_value-gross)>Decimal("0.02"):
        raise ValueError("PAPER_NAV_DOES_NOT_RECONCILE_TO_MARKS")
    total_tax_ils=book.tax_assessed_ils
    terminal_net=nominal_cash_on_exit-total_tax_ils/fx_today
    if terminal_net < 0 or terminal_net > gross:
        raise ValueError("INVALID_TERMINAL_AFTER_TAX_EQUITY")
    return {
        "schema_version":1,
        "kind":"STOCKLENS_TAX_STATUS_V1",
        "status":"RESEARCH_COMPLETE",
        "source":"PRIVATE_SHA_VERIFIED_ST_PAPER",
        "asof_date":day,
        "receipt_sha256":receipt_sha,
        "fx_evidence_sha256":_fx_hash(fx),
        "fx_verified":True,  # explicitly HUMAN-ATTESTED; not independent API parity
        "fx_attestation_scope":"HUMAN_ATTESTED_SOURCE_NOT_AUTOMATICALLY_VERIFIED",
        "lot_history_verified":True,
        "broker_withholding_verified":False,
        "capital_trading_authorized":False,
        "gross_paper_nav_usd":float(gross),
        "estimated_after_tax_liquidation_usd":float(terminal_net),
        "estimated_tax_assessed_ils":float(pre_tax),
        "estimated_total_tax_if_liquidated_ils":float(total_tax_ils),
        "estimated_additional_exit_tax_ils":float(total_tax_ils-pre_tax),
        "actual_broker_tax_withheld_ils":None,
        "assumed_tax_rate":0.25,
        "lot_basis":"FIFO_RESEARCH_FX_APPROXIMATION",
        "note":"MODELED ONLY. Never actual Excellence withholding. No surcharge, annual broker reconciliation or independent FX issuer validation."
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--receipt",required=True)
    ap.add_argument("--receipt-sha",required=True)
    ap.add_argument("--fx",required=True)
    ap.add_argument("--fx-attestation",required=True)
    ap.add_argument("--out",required=True)
    args=ap.parse_args()
    target=Path(args.out).resolve()
    # The public GitHub and Amplify docs folder must NEVER contain private
    # account receipts, broker tax lots or FX evidence.
    if target.is_relative_to((Path.cwd()/"docs").resolve()) or target.is_relative_to((Path.cwd()/"research").resolve()):
        raise SystemExit("REFUSE_PUBLIC_GIT_OR_RESEARCH_OUTPUT")
    fx=json.loads(Path(args.fx).read_text(encoding="utf-8"))
    attestation=json.loads(Path(args.fx_attestation).read_text(encoding="utf-8"))
    report=build(Path(args.receipt).read_bytes(),args.receipt_sha,fx,attestation)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("PRIVATE_TAX_RESEARCH_READY",report["asof_date"],"NO_AWS_WRITES")
if __name__=="__main__":
    main()

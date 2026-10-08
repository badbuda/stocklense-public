from __future__ import annotations
import csv,json,math
from pathlib import Path
from json_artifacts import write_json_atomic

def _f(x):
    try:return float(x or 0)
    except:return 0.0

def build_cost_attribution(ledger="paper_portfolio/ledger.csv",trades="paper_portfolio/trades.csv",out="shadow_history/cost_attribution.json"):
    p=Path(ledger);rows=list(csv.DictReader(p.open())) if p.exists() else []
    tp=Path(trades);trs=list(csv.DictReader(tp.open())) if tp.exists() else []
    if not rows:r={"status":"WAITING_FOR_PROSPECTIVE_DATA","sessions":0,"execution_audit_required":True}
    else:
        try:audit=json.loads(Path("shadow_history/execution_audit.json").read_text())
        except Exception:audit={}
        ledger_fees=_f(rows[-1].get("cumulative_fees"));ledger_slip=_f(rows[-1].get("cumulative_slippage_cost"));div=_f(rows[-1].get("cumulative_dividends"));eq0=_f(rows[0].get("equity"))
        trade_fees=sum(_f(x.get("fee")) for x in trs);trade_slip=sum(_f(x.get("modeled_slippage_cost")) for x in trs)
        costs_reconciled=math.isclose(ledger_fees,trade_fees,rel_tol=0,abs_tol=1e-8) and math.isclose(ledger_slip,trade_slip,rel_tol=0,abs_tol=1e-8)
        verified=audit.get("status")=="PASS" and costs_reconciled
        fees=trade_fees;slip=trade_slip
        r={"status":"ACTIVE_VERIFIED" if verified else "BLOCKED_UNVERIFIED_ACCOUNTING","sessions":len(rows),"trade_count":len(trs),
           "execution_audit_status":audit.get("status","MISSING"),"costs_reconciled_to_trades":costs_reconciled,
           "fees":fees,"modeled_slippage":slip,"dividends":div,"net_accounting_adjustment":div-fees-slip,
           "fee_share_of_cost":fees/(fees+slip) if fees+slip else None,"slippage_share_of_cost":slip/(fees+slip) if fees+slip else None,
           "net_adjustment_pct_of_first_equity":(div-fees-slip)/eq0*100 if eq0 else None,
           "broker_execution_costs":False,"semantics":"Verified modeled paper costs only; not observed broker execution costs."}
    write_json_atomic(out,r);return r
if __name__=="__main__":print(json.dumps(build_cost_attribution(),indent=2))

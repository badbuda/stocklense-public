from __future__ import annotations
import csv,json,hashlib
from pathlib import Path
from json_artifacts import write_json_atomic
from paper_execution_contract import fingerprint as execution_contract_sha256
from stocklens.paper import FEE_BPS,SLIPPAGE_BPS

def _policy():
    p={"fee_bps":FEE_BPS,"slippage_bps":SLIPPAGE_BPS,"reductions_time_et":"09:31","additions_time_et":"09:32","mode":"PROSPECTIVE_PAPER"}
    p["policy_sha256"]=hashlib.sha256(json.dumps(p,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return p

def build_trade_receipts(trades="paper_portfolio/trades.csv",out="shadow_history/trade_receipts.json"):
    p=Path(trades);rows=list(csv.DictReader(p.open())) if p.exists() else [];items=[];policy=_policy()
    for r in rows:
        core={k:r.get(k) for k in ("execution_session","signal_date","symbol","side","qty","time_et","reference_price","modeled_fill_price","gross_notional","fee","modeled_slippage_cost","fee_bps","slippage_bps")}
        rid=hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()[:20]
        items.append({"receipt_id":rid,**core,"modeled":True,"execution_source":"paper_portfolio/trades.csv","policy_sha256":policy["policy_sha256"]})
    result={"schema_version":3,"status":"ACTIVE" if items else "WAITING_FOR_TRADES","trade_count":len(items),"execution_contract_sha256":execution_contract_sha256(),"execution_policy":policy,"receipts":items[-100:],"broker_confirmation":False,"note":"Deterministic receipts derived from prospective paper trades; not broker confirmations."}
    write_json_atomic(out,result);return result
if __name__=="__main__":print(json.dumps(build_trade_receipts(),indent=2))

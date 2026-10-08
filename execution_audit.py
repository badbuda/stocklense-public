from __future__ import annotations
import csv,json,math,hashlib
from stocklens.paper import FEE_BPS,SLIPPAGE_BPS
from pathlib import Path
from json_artifacts import write_json_atomic
from paper_execution_contract import fingerprint as execution_contract_sha256
def _f(x):
    try:return float(x)
    except:return 0.0
def build_execution_audit(ledger="paper_portfolio/ledger.csv",trades="paper_portfolio/trades.csv",out="shadow_history/execution_audit.json"):
    lp=Path(ledger);rows=list(csv.DictReader(lp.open())) if lp.exists() else []
    tp=Path(trades);trs=list(csv.DictReader(tp.open())) if tp.exists() else []
    problems=[];by={}
    contract_sha=execution_contract_sha256()
    try:
        plan=json.loads(Path("shadow_history/execution_plan.json").read_text())
        if plan.get("execution_contract_sha256")!=contract_sha:problems.append("EXECUTION_PLAN_CONTRACT_MISMATCH")
    except Exception:problems.append("EXECUTION_PLAN_CONTRACT_MISSING")
    try:
        receipts=json.loads(Path("shadow_history/trade_receipts.json").read_text())
        if receipts.get("execution_contract_sha256")!=contract_sha:problems.append("TRADE_RECEIPTS_CONTRACT_MISMATCH")
        receipt_items=receipts.get("receipts",[])
        if receipts.get("trade_count")!=len(trs):problems.append("TRADE_RECEIPT_COUNT_MISMATCH")
        expected_receipts=min(len(trs),100)
        if len(receipt_items)!=expected_receipts:problems.append("TRADE_RECEIPT_WINDOW_COUNT_MISMATCH")
        if any(x.get("modeled") is not True or x.get("execution_source")!="paper_portfolio/trades.csv" for x in receipt_items):problems.append("TRADE_RECEIPT_PROVENANCE_MISMATCH")
        receipt_ids=[x.get("receipt_id") for x in receipt_items]
        expected_items=[]
        for t in trs[-100:]:
            core={k:t.get(k) for k in ("execution_session","signal_date","symbol","side","qty","time_et","reference_price","modeled_fill_price","gross_notional","fee","modeled_slippage_cost","fee_bps","slippage_bps")}
            expected_items.append(hashlib.sha256(json.dumps(core,sort_keys=True,separators=(",",":")).encode()).hexdigest()[:20])
        if receipt_ids!=expected_items:problems.append("TRADE_RECEIPT_CONTENT_MISMATCH")
        if len(receipt_ids)!=len(set(receipt_ids)):problems.append("DUPLICATE_TRADE_RECEIPT_ID")
    except Exception:problems.append("TRADE_RECEIPTS_CONTRACT_MISSING")
    for t in trs:
        sess=t["execution_session"];by.setdefault(sess,[]).append(t)
        ref=_f(t["reference_price"]);fill=_f(t["modeled_fill_price"]);side=t["side"];qty=_f(t["qty"]);slip=SLIPPAGE_BPS/10000.0;expected=ref*(1+slip if side=="BUY" else 1-slip)
        if not math.isclose(fill,expected,rel_tol=0,abs_tol=1e-8):problems.append(f"FILL_MODEL_MISMATCH:{sess}:{t['symbol']}")
        if _f(t["fee_bps"])!=FEE_BPS or _f(t["slippage_bps"])!=SLIPPAGE_BPS:problems.append(f"COST_ASSUMPTION_MISMATCH:{sess}:{t['symbol']}")
        expected_fee=_f(t["gross_notional"])*(FEE_BPS/10000.0)
        expected_slippage=abs(fill-ref)*qty
        if not math.isclose(_f(t["fee"]),expected_fee,rel_tol=0,abs_tol=1e-8):problems.append(f"FEE_AMOUNT_MISMATCH:{sess}:{t['symbol']}")
        if not math.isclose(_f(t["modeled_slippage_cost"]),expected_slippage,rel_tol=0,abs_tol=1e-8):problems.append(f"SLIPPAGE_AMOUNT_MISMATCH:{sess}:{t['symbol']}")
    running_fees=0.0;running_slippage=0.0;running_dividends=0.0
    previous_cash=None
    for r in rows:
        sess=r["session_date"];session_trades=by.get(sess,[])
        n=int(float(r.get("trade_count_session") or 0));actual=len(session_trades)
        if n!=actual:problems.append(f"TRADE_COUNT_MISMATCH:{sess}:{n}:{actual}")
        running_fees+=sum(_f(t.get("fee")) for t in session_trades)
        session_dividends=_f(r.get("dividends_credited_session"));running_dividends+=session_dividends
        running_slippage+=sum(_f(t.get("modeled_slippage_cost")) for t in session_trades)
        if not math.isclose(_f(r.get("cumulative_fees")),running_fees,rel_tol=0,abs_tol=1e-8):problems.append(f"CUMULATIVE_FEE_MISMATCH:{sess}")
        if not math.isclose(_f(r.get("cumulative_slippage_cost")),running_slippage,rel_tol=0,abs_tol=1e-8):problems.append(f"CUMULATIVE_SLIPPAGE_MISMATCH:{sess}")
        if not math.isclose(_f(r.get("cumulative_dividends")),running_dividends,rel_tol=0,abs_tol=1e-8):problems.append(f"CUMULATIVE_DIVIDEND_MISMATCH:{sess}")
        if previous_cash is None:
            initial_cash=_f(r.get("cash"))-session_dividends
            for t in session_trades: initial_cash-= (_f(t.get("gross_notional"))-_f(t.get("fee"))) if t.get("side")=="SELL" else -(_f(t.get("gross_notional"))+_f(t.get("fee")))
            expected_initial=100000.0
            if not math.isclose(initial_cash,expected_initial,rel_tol=0,abs_tol=1e-6):problems.append(f"INITIAL_CASH_FLOW_MISMATCH:{sess}")
        else:
            expected_cash=previous_cash+session_dividends
            for t in session_trades: expected_cash+= (_f(t.get("gross_notional"))-_f(t.get("fee"))) if t.get("side")=="SELL" else -(_f(t.get("gross_notional"))+_f(t.get("fee")))
            if not math.isclose(_f(r.get("cash")),expected_cash,rel_tol=0,abs_tol=1e-6):problems.append(f"CASH_FLOW_RECONCILIATION_MISMATCH:{sess}")
        previous_cash=_f(r.get("cash"))
        equity=_f(r.get("cash"))+_f(r.get("qqq_shares"))*_f(r.get("qqq_close"))+_f(r.get("tqqq_shares"))*_f(r.get("tqqq_close"))
        if not math.isclose(_f(r.get("equity")),equity,rel_tol=0,abs_tol=1e-6):problems.append(f"EQUITY_RECONCILIATION_MISMATCH:{sess}")
        turnover=sum(_f(t.get("gross_notional")) for t in session_trades)
        if not math.isclose(_f(r.get("turnover_notional")),turnover,rel_tol=0,abs_tol=1e-8):problems.append(f"TURNOVER_RECONCILIATION_MISMATCH:{sess}")
    if rows:
        try:
            state=json.loads(Path("paper_portfolio/state.json").read_text())
            last=rows[-1]
            if not math.isclose(_f(state.get("cash")),_f(last.get("cash")),rel_tol=0,abs_tol=1e-8):problems.append("STATE_LEDGER_CASH_MISMATCH")
            shares=state.get("shares",{})
            if int(shares.get("QQQ",0))!=int(float(last.get("qqq_shares") or 0)):problems.append("STATE_LEDGER_QQQ_SHARES_MISMATCH")
            if int(shares.get("TQQQ",0))!=int(float(last.get("tqqq_shares") or 0)):problems.append("STATE_LEDGER_TQQQ_SHARES_MISMATCH")
            if state.get("last_mark_session")!=last.get("session_date"):problems.append("STATE_LEDGER_SESSION_MISMATCH")
            if state.get("last_executed_signal_date")!=last.get("signal_date"):problems.append("STATE_LEDGER_SIGNAL_MISMATCH")
            if not math.isclose(_f(state.get("cumulative_fees")),_f(last.get("cumulative_fees")),rel_tol=0,abs_tol=1e-8):problems.append("STATE_LEDGER_FEE_MISMATCH")
            if not math.isclose(_f(state.get("cumulative_slippage_cost")),_f(last.get("cumulative_slippage_cost")),rel_tol=0,abs_tol=1e-8):problems.append("STATE_LEDGER_SLIPPAGE_MISMATCH")
            if not math.isclose(_f(state.get("last_equity")),_f(last.get("equity")),rel_tol=0,abs_tol=1e-6):problems.append("STATE_LEDGER_EQUITY_MISMATCH")
            if not math.isclose(_f(state.get("peak_equity")),_f(last.get("peak_equity")),rel_tol=0,abs_tol=1e-6):problems.append("STATE_LEDGER_PEAK_EQUITY_MISMATCH")
            if not math.isclose(_f(state.get("cumulative_dividends")),_f(last.get("cumulative_dividends")),rel_tol=0,abs_tol=1e-8):problems.append("STATE_LEDGER_DIVIDENDS_MISMATCH")
            if int(state.get("trade_count",0))!=len(trs):problems.append("STATE_TRADE_COUNT_MISMATCH")
        except Exception:problems.append("PAPER_STATE_MISSING_OR_INVALID")
    result={"status":"PASS" if not problems else "FAIL","ledger_sessions":len(rows),"trades":len(trs),"problems":problems[:50],"policy":{"fee_bps":FEE_BPS,"slippage_bps":SLIPPAGE_BPS},"execution_contract_sha256":contract_sha,"checks":["modeled fill matches canonical slippage policy","fee/slippage assumptions match canonical paper policy","fee amount reconciles to gross notional","slippage amount reconciles to reference-vs-fill delta","ledger session trade count equals trade log","cumulative fees/slippage reconcile to trade log","cash flow reconciles from canonical initial equity through trades and dividends","cumulative dividends reconcile to session credits","ledger equity reconciles to cash plus marked holdings","turnover reconciles to session trade notionals","terminal state equity/peak/dividends/trade count reconcile to ledger and trade log"]}
    write_json_atomic(out,result)
    if problems:raise RuntimeError("EXECUTION_AUDIT_FAIL:"+",".join(problems[:5]))
    return result
if __name__=="__main__":print(json.dumps(build_execution_audit(),indent=2))

"""Independent prospective paper audit; an observed minute-bar simulation, never broker fills."""
from __future__ import annotations
import csv,json,math
from datetime import date,datetime,time,timezone
from pathlib import Path
from zoneinfo import ZoneInfo
NY=ZoneInfo("America/New_York")
SYMBOLS=("QQQ","TQQQ")
FEE_BPS=2.0
SLIPPAGE_BPS=10.0

def numeric(row,key):
    x=float(row[key])
    if not math.isfinite(x): raise ValueError("NONFINITE:"+key)
    return x

def near(a,b,atol=.025):
    return math.isclose(a,b,rel_tol=1e-8,abs_tol=atol)

def csv_rows(path):
    p=Path(path)
    if not p.is_file(): return []
    with p.open(newline="",encoding="utf-8") as f: return list(csv.DictReader(f))

def evaluate(ledger,trades,snapshots):
    errors=[]
    dates=[r.get("session_date","") for r in ledger]
    if dates!=sorted(set(dates)) or not all(dates): errors.append("DUPLICATE_OR_UNORDERED_SESSION")
    by_date={x:[] for x in dates}
    for trade in trades:
        day=trade.get("execution_session","")
        if day not in by_date: errors.append("ORPHAN_TRADE:"+day)
        else: by_date[day].append(trade)
    cumulative_fees=cumulative_slip=0.
    # Independently reconstruct the full paper account from 100k inception,
    # not merely compare closing NAV against the reported holdings.
    replay_cash=100000.0
    replay_shares={symbol:0 for symbol in SYMBOLS}
    prior=None
    equity=None
    for row in ledger:
        day=row.get("session_date","")
        if not day: continue
        try:
            dt=date.fromisoformat(day)
            signal=date.fromisoformat(row["signal_date"])
            if signal>=dt: errors.append("SIGNAL_SAME_SESSION_OR_FUTURE:"+day)
            snap=snapshots.get(signal.isoformat())
            if snap is None: errors.append("MISSING_SIGNAL_SNAPSHOT:"+day)
            else:
                stamp=datetime.fromisoformat(snap["generated_at_utc"].replace("Z","+00:00"))
                market_open=datetime.combine(dt,time(9,30),tzinfo=NY)
                if stamp.tzinfo is None or stamp.astimezone(timezone.utc)>=market_open.astimezone(timezone.utc):
                    errors.append("SIGNAL_LOOKAHEAD:"+day)
                target=snap.get("latest",{})
                if snap.get("mode")!="SHADOW_ONLY_NO_BROKER_ACTIONS" or target.get("asof_date")!=signal.isoformat():
                    errors.append("INVALID_OR_LATE_FROZEN_SIGNAL:"+day)
                for key in ("qqq_weight","tqqq_weight"):
                    if not near(float(target[key]),numeric(row,"target_"+key),1e-9):
                        errors.append("TARGET_MISMATCH:"+day+":"+key)
                if not near(float(target["target_leverage"]),numeric(row,"target_leverage"),1e-9):
                    errors.append("LEVERAGE_MISMATCH:"+day)
            if row.get("execution_source")!="YFINANCE_1M_RAW":
                errors.append("SYNTHETIC_OR_UNKNOWN_SOURCE:"+day)
            cash=numeric(row,"cash")
            shares={s:int(row[s.lower()+"_shares"]) for s in SYMBOLS}
            if cash<-.025 or min(shares.values())<0: errors.append("NEGATIVE_HOLDINGS:"+day)
            equity=cash+sum(shares[s]*numeric(row,s.lower()+"_close") for s in SYMBOLS)
            if not near(equity,numeric(row,"equity")): errors.append("EQUITY_INVALID:"+day)
            if not near(equity/100000-1,numeric(row,"cumulative_return"),1e-7):
                errors.append("RETURN_INVALID:"+day)
            if numeric(row,"fee_bps")!=FEE_BPS or numeric(row,"slippage_bps")!=SLIPPAGE_BPS:
                errors.append("CHANGED_COST_POLICY:"+day)
            turnover=fees=slip=0.
            for tr in by_date[day]:
                symbol,side=tr["symbol"],tr["side"]
                if symbol not in SYMBOLS or side not in ("BUY","SELL"):
                    errors.append("BAD_ORDER:"+day);continue
                if tr.get("signal_date")!=row["signal_date"]: errors.append("WRONG_TRADE_SIGNAL:"+day)
                if tr.get("time_et")!=("09:31" if side=="SELL" else "09:32"):
                    errors.append("WRONG_EXECUTION_WINDOW:"+day)
                qty=int(tr["qty"]);ref=numeric(tr,"reference_price");fill=numeric(tr,"modeled_fill_price")
                if qty<=0 or min(ref,fill)<=0: errors.append("INVALID_PAPER_QTY_OR_PRICE:"+day)
                expected=ref*(1+(1 if side=="BUY" else -1)*SLIPPAGE_BPS/10000)
                if not near(fill,expected,1e-7): errors.append("INVALID_MODELLED_FILL:"+day)
                gross=numeric(tr,"gross_notional");fee=numeric(tr,"fee")
                model_slip=numeric(tr,"modeled_slippage_cost")
                if not near(gross,qty*fill,1e-6) or not near(fee,gross*FEE_BPS/10000,1e-6):
                    errors.append("INVALID_TRADE_FEE_NOTIONAL:"+day)
                if not near(model_slip,abs(fill-ref)*qty,1e-6):
                    errors.append("INVALID_TRADE_SLIPPAGE:"+day)
                # Independently replay cash, trade fees and whole-share inventory.
                if side=="BUY":
                    replay_cash-=gross+fee
                    replay_shares[symbol]+=qty
                else:
                    if qty>replay_shares[symbol]:
                        errors.append("REPLAY_SELL_EXCEEDS_HOLDINGS:"+day)
                    replay_cash+=gross-fee
                    replay_shares[symbol]-=qty
                turnover+=gross;fees+=fee;slip+=model_slip
            replay_cash+=numeric(row,"dividends_credited_session")
            if not near(replay_cash,cash):
                errors.append(("CASH_CONSERVATION_INVALID:" if prior else "INCEPTION_CASH_INVALID:")+day)
            if replay_shares!=shares:
                errors.append(("SHARES_CONSERVATION_INVALID:" if prior else "INCEPTION_SHARES_INVALID:")+day)
            if len(by_date[day])!=int(row["trade_count_session"]): errors.append("TRADE_COUNT_INVALID:"+day)
            if not near(turnover,numeric(row,"turnover_notional")):
                errors.append("TURNOVER_INVALID:"+day)
            cumulative_fees+=fees;cumulative_slip+=slip
            if not near(cumulative_fees,numeric(row,"cumulative_fees")):
                errors.append("CUMULATIVE_FEES_INVALID:"+day)
            if not near(cumulative_slip,numeric(row,"cumulative_slippage_cost")):
                errors.append("CUMULATIVE_SLIPPAGE_INVALID:"+day)
            if prior:
                cash_delta=sum((1 if t["side"]=="SELL" else -1)*numeric(t,"gross_notional")-numeric(t,"fee") for t in by_date[day])
                expected_cash=numeric(prior,"cash")+cash_delta+numeric(row,"dividends_credited_session")
                if not near(cash,expected_cash): errors.append("CASH_CONSERVATION_INVALID:"+day)
            prior=row
        except (ValueError,KeyError,TypeError,OverflowError) as exc:
            errors.append("INVALID_PAPER_ROW:"+day+":"+type(exc).__name__)
    status=("FAIL" if errors else "WAITING_FOR_PROSPECTIVE_PAPER" if not ledger else
            "PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS")
    return {"schema_version":1,"status":status,
            "verified_paper_sessions":len(ledger) if not errors else 0,
            "latest_session":dates[-1] if dates and not errors else None,
            "modeled_trades":len(trades) if not errors else 0,
            "equity":equity if not errors else None,"errors":sorted(set(errors)),
            "data_source":"YFINANCE_1M_RAW",
            "broker_fills_observed":False,"live_trading_authorized":False,
            "inception_cash_and_holdings_replayed":bool(ledger) and not errors,
            "quote_bid_ask_proven":False,
            "independent_vendor_close_proven":False,
            "note":"Cash and share inventory replayed independently from modeled receipts, including inception. Yahoo minute opens are not independently verified broker fills or bid/ask quotes."}

def build(out="docs/paper_portfolio_integrity.json"):
    ledger=csv_rows("paper_portfolio/ledger.csv");trades=csv_rows("paper_portfolio/trades.csv")
    snapshots={}
    for row in ledger:
        signal=row.get("signal_date")
        if signal and signal not in snapshots:
            p=Path("shadow_history")/(signal+".json")
            snapshots[signal]=json.loads(p.read_text()) if p.is_file() else None
    result=evaluate(ledger,trades,snapshots)
    p=Path(out);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(result))
    if result["status"]=="FAIL":
        raise RuntimeError("PAPER_ACCOUNTING_FAIL_CLOSED:"+",".join(result["errors"]))
    return result

if __name__=="__main__":build()

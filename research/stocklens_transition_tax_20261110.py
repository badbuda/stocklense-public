"""StockLens: explicit FIFO / FX Israeli capital-gains tax counterfactual.

Runs the EXACT target series exported by the frozen StockLens 8.0 transition
timing experiment. Uses real observed adjusted QQQ/TQQQ ETF prices and observed
Yahoo USD/ILS close-asof, no synthetic returns. Uses existing repo TaxBook for
25% FX-indexed Israeli capital gains research, NOT a tax return or legal opinion.

Models two comparative scenarios:
  gross: same fills & allocation as frozen timing research, no withholding.
  immediate: withhold the TaxBook's positive incremental assessment on each sale
             from investment cash in USD at the day's historical FX.
  deferred: DO NOT debit assessed tax during backtest; terminal subtract prior
            estimated obligations and hypothetical liquidation assessment. This
            is not legally permitted tax deferral; an upper-bound counterfactual.
Fixed, independent initial $100k per candidate, no contributions and zero cash
yield; 2bps fees and 10bps slippage per side. Historical next-open proxy.
"""
from __future__ import annotations
import bisect
import copy
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
from stocklens.tax_research import TaxBook

SRC = Path("research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json")
LEV = Path("transition-timing-results.json")
FX_FILE = Path("research/results/usdils_vendor_20261110.json")
OUT = Path("research/results/transition_tax_fifo_fx_20261110.json")
CAP = 100000.0
INV = 0.985
FEE = 0.0002
SLIP = 0.001
RATE = 0.25
SYMS = ("QQQ", "TQQQ")
START = 200
EXPECTED_SNAPSHOT = "bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129"


def acquire_fx():
    import yfinance as yf
    frame = yf.Ticker("ILS=X").history(
        start="2010-11-15", end="2026-10-12",
        interval="1d", auto_adjust=True, repair=False, actions=False
    )
    if frame is None or frame.empty:
        raise ValueError("USDILS_VENDOR_EMPTY")
    items = []
    for timestamp, record in frame.iterrows():
        date = timestamp.date().isoformat()
        if date > "2026-10-09":
            continue
        v = float(record["Close"])
        if not math.isfinite(v) or not 2.0 < v < 6.0:
            raise ValueError(f"USDILS_INVALID_QUOTE:{date}:{v}")
        items.append({"date": date, "ils_per_usd": v})
    d = [x["date"] for x in items]
    if len(d) < 3600 or d != sorted(set(d)) or d[-1] < "2026-10-08":
        raise ValueError(f"USDILS_HISTORY_INSUFFICIENT:{len(d)}:{d[-1:]}")
    sha = hashlib.sha256(json.dumps(items,sort_keys=True,separators=(",",":")).encode()).hexdigest()
    return {
        "kind": "YAHOO_USDILS_DAILY_OBSERVED_CLOSE_ASOF",
        "captured_utc": datetime.now(timezone.utc).isoformat(),
        "source": "Yahoo Finance / ILS=X USD/ILS",
        "independent_vendor_parity": False,
        "quotes": items, "sha256": sha
    }


def validate(source, levels, fx):
    rows = source["daily"]
    assert source["snapshot_sha256"] == EXPECTED_SNAPSHOT
    assert len(rows) == 4191
    assert levels["source_snapshot_sha256"] == EXPECTED_SNAPSHOT
    assert levels["window"]["sessions"] == 3991
    assert levels["window"]["start"] == rows[START]["date"]
    assert levels["window"]["end"] == rows[-1]["date"]
    names = [v["name"] for v in levels["combinations"]]
    assert len(names) == 8 and len(set(names)) == 8
    signals = levels.get("target_level_series")
    if not signals or set(signals) != set(names):
        raise ValueError("MISSING_EXACT_EXECUTED_SIGNAL_SERIES")
    dates = [r["date"] for r in rows]
    assert dates == sorted(set(dates))
    for name in names:
        x = signals[name]
        assert len(x) == len(rows) - START
        for i, level in enumerate(x):
            assert level in (0, 1.25, 2, 3)
            if rows[START+i]["l"] == 0:
                assert level == 0
    x_dates = [v["date"] for v in fx["quotes"]]
    x_rates = [float(v["ils_per_usd"]) for v in fx["quotes"]]
    if x_dates != sorted(set(x_dates)):
        raise ValueError("BAD_FX_SERIES_SORT")
    mapping = {}
    worst_age = 0
    for day in dates[START:]:
        idx = bisect.bisect_right(x_dates, day)-1
        if idx < 0:
            raise ValueError("NO_INITIAL_FX")
        age = (datetime.fromisoformat(day)-datetime.fromisoformat(x_dates[idx])).days
        if age > 5:
            raise ValueError(f"USDILS_ASOF_TOO_STALE:{day}:{x_dates[idx]}")
        worst_age = max(worst_age, age)
        mapping[day] = x_rates[idx]
    return names, signals, mapping, worst_age


def replay(rows, lev, fx, withhold):
    from collections import Counter
    book = TaxBook(rate=str(RATE))
    cash=CAP
    shares={"QQQ":0,"TQQQ":0}
    previous=None
    trades=0
    buys=sells=0
    total_notional=0.0
    navs=[]
    taxes_withheld_usd=0.0
    taxes_withheld_ils=0.0
    last_day=None

    def sell(day,sym,qty,open_price,rate):
        nonlocal cash,trades,sells,total_notional,taxes_withheld_usd,taxes_withheld_ils
        if qty<=0:return
        assert qty<=shares[sym]
        fill=open_price*(1-SLIP)
        commission=qty*fill*FEE
        response=book.sell(day,sym,int(qty),fill,commission,rate)
        cash+=qty*fill-commission
        shares[sym]-=qty
        trades+=1;sells+=1;total_notional+=qty*open_price
        tax=float(response["estimated_incremental_tax_ils"])
        if withhold:
            amount_usd=tax/rate
            cash-=amount_usd
            taxes_withheld_usd+=amount_usd
            taxes_withheld_ils+=tax
        if cash < -0.001:
            raise ValueError(f"NEGATIVE_CASH_AFTER_SELL_AND_TAX:{day}:{sym}")

    def buy(day,sym,qty,open_price,rate):
        nonlocal cash,trades,buys,total_notional
        if qty<=0:return
        fill=open_price*(1+SLIP)
        unit=fill*(1+FEE)
        qty=int(min(qty, math.floor(max(0,cash)/unit)))
        if qty<=0:return
        book.buy(day,sym,qty,fill,qty*fill*FEE,rate)
        cash-=qty*unit
        shares[sym]+=qty
        trades+=1;buys+=1;total_notional+=qty*open_price

    for offset,row in enumerate(rows[START:]):
        day=row["date"]
        rate=fx[day]
        level=lev[offset]
        if previous is None or previous!=level:
            equity=cash+shares["QQQ"]*row["qo"]+shares["TQQQ"]*row["to"]
            w_t=(level-1)/2 if level else 0.0
            w_q=1-w_t if level else 0.0
            target_q=math.floor(equity*INV*w_q/row["qo"])
            target_t=math.floor(equity*INV*w_t/row["to"])
            sell(day,"QQQ",max(0,shares["QQQ"]-target_q),row["qo"],rate)
            sell(day,"TQQQ",max(0,shares["TQQQ"]-target_t),row["to"],rate)
            buy(day,"QQQ",max(0,target_q-shares["QQQ"]),row["qo"],rate)
            buy(day,"TQQQ",max(0,target_t-shares["TQQQ"]),row["to"],rate)
        if any(book.quantity(s)!=shares[s] for s in SYMS):
            raise ValueError(f"BOOK_POSITION_DIVERGENCE:{day}")
        nav=cash+shares["QQQ"]*row["qc"]+shares["TQQQ"]*row["tc"]
        if nav<=0 or not math.isfinite(nav) or cash<-0.001:
            raise ValueError(f"INVALID_NAV:{day}")
        navs.append(nav)
        previous=level
        last_day=day

    final_rate=fx[last_day]
    liquidation=copy.deepcopy(book)
    final_row=rows[-1]
    proceeds=0.0
    for sym,prefix in (("QQQ","q"),("TQQQ","t")):
        qty=shares[sym]
        if qty:
            price=final_row[prefix+"c"]*(1-SLIP)
            fee=qty*price*FEE
            liquidation.sell(last_day,sym,qty,price,fee,final_rate)
            proceeds+=qty*price-fee
    liquid_tax_ils=float(liquidation.tax_assessed_ils-book.tax_assessed_ils)
    if liquid_tax_ils < -0.001:raise ValueError("NEGATIVE_INCREMENTAL_LIQUIDATION_TAX")
    prior_unpaid_ils=0.0 if withhold else float(book.tax_assessed_ils)
    terminal_net=cash+proceeds-(liquid_tax_ils+prior_unpaid_ils)/final_rate
    if terminal_net<=0:raise ValueError("INSOLVENT_AFTER_TAX")
    terminal_gross=cash+proceeds
    years=(datetime.fromisoformat(last_day)-datetime.fromisoformat(rows[START]["date"])).days/365.2425
    peak=CAP
    dd=0.0
    for v in navs:
        peak=max(peak,v);dd=min(dd,v/peak-1)
    return {
        "end_gross_or_tax_debited_nav_usd":navs[-1],
        "after_tax_terminal_liquidation_usd":terminal_net,
        "terminal_pre_liquidation_tax_nav_usd":terminal_gross,
        "after_tax_terminal_cagr":(terminal_net/CAP)**(1/years)-1,
        "interim_nav_maxdd":dd,
        "trades":trades,"buys":buys,"sells":sells,"turnover_notional_usd":total_notional,
        "estimated_sales_tax_ils":float(book.tax_assessed_ils),
        "estimated_tax_withheld_ils":taxes_withheld_ils,
        "estimated_tax_withheld_usd":taxes_withheld_usd,
        "estimated_liquidation_tax_ils":liquid_tax_ils,
        "unpaid_prior_assessment_ils":prior_unpaid_ils,
        "tax_loss_carry_ils":float(liquidation.losses),
        "final_fx_ils_per_usd":final_rate,
        "tax_model":"repo TaxBook FIFO/FX approximation, 25% eligible nominal vs FX indexed gain/loss",
    }


def main():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    try:
        src=json.loads(SRC.read_text())
        lv=json.loads(LEV.read_text())
        fx=acquire_fx()
        FX_FILE.write_text(json.dumps(fx,indent=2,sort_keys=True)+"\n")
        names,targets,map_fx,age=validate(src,lv,fx)
        results=[]
        for n in names:
            gross=replay(src["daily"],targets[n],map_fx,False)
            immediate=replay(src["daily"],targets[n],map_fx,True)
            ref=next(x for x in lv["combinations"] if x["name"]==n)
            # exact parity with original JS replay WITHOUT tax withholding
            denom=max(1.0,abs(ref["terminal_equity"]))
            relative=(gross["end_gross_or_tax_debited_nav_usd"]-ref["terminal_equity"])/denom
            if abs(relative)>1e-9 or gross["trades"]!=ref["trades"]:
                raise ValueError(f"PRETAX_DAILY_REPLAY_PARITY_FAILED:{n}:relative={relative},count={gross['trades']}/{ref['trades']}")
            results.append({
                "name":n,"gross_parity":True,
                "original_pretax_cagr":ref["cagr"],
                "original_pretax_equity":ref["terminal_equity"],
                "immediate_withholding":immediate,
                "deferred_only_counterfactual":gross,
            })
        baseline=results[0]["immediate_withholding"]["after_tax_terminal_cagr"]
        for row in results:
            row["after_tax_immediate_delta_vs_frozen_pp"]=100*(
                row["immediate_withholding"]["after_tax_terminal_cagr"]-baseline)
        outcome={
            "status":"OBSERVED_USDILS_AND_FIFO_FX_TAX_RESEARCH",
            "source":"frozen observed QQQ/TQQQ and independently fetched Yahoo daily USDILS",
            "fx_vendor_sha256":fx["sha256"],"fx_vendor_parity":False,
            "fx_quotes":len(fx["quotes"]),"max_asof_fx_age_calendar_days":age,
            "tax_rate":RATE,
            "window":lv["window"],
            "cohort_replay_parity":True,
            "immediate_case":"Taxes on profitable sales deducted immediately from cash; no tax refund for later losses; carried loss pool.",
            "deferred_case":"Gross holdings compound with tax accrued; all past assessments deducted only at terminal. COUNTERFACTUAL not legal deferral.",
            "limitations":[
                "Research approximation, not actual Israeli broker withholding or an accountant-certified tax calculation.",
                "TaxBook FX-indexed capital-gains treatment is a repo scenario, not tax law conclusive for each instrument/account.",
                "No verification of tax loss carryover legal filing, annual reconciliation, surtax, fees on FX conversion, inflation adjustments, dividends, or external portfolio losses.",
                "Uses split/dividend-adjusted ETF prices and synthetic whole-share convention: not raw broker tax lots.",
                "FX day as-of Yahoo close, not verified exact execution-timestamp FX; no independent second provider.",
                "No model of intra-year tax refunds; no contributions; zero cash interest; frozen historical reused sample (not pristine OOS)."
            ],
            "results":results,"automatic_promotion":False,"production_changed":False,"broker_orders":False
        }
    except Exception as exc:
        outcome={
            "status":"BLOCKED_FX_TAX_OR_PARITY",
            "reason":str(exc)[:1000],
            "results":[],
            "automatic_promotion":False,"production_changed":False,"broker_orders":False
        }
    OUT.write_text(json.dumps(outcome,indent=2,sort_keys=True)+"\n")
    print("TRANSITION_TAX_STATUS="+outcome["status"])
    if outcome.get("results"):
        for row in outcome["results"]:
            r=row["immediate_withholding"]
            print("TAX_CASE",row["name"],"after_tax_cagr",round(100*r["after_tax_terminal_cagr"],3),
                  "after_tax_terminal_usd",round(r["after_tax_terminal_liquidation_usd"],2),
                  "trades",r["trades"],"tax_paid_ils",round(r["estimated_tax_withheld_ils"],2),
                  "vs_baseline_pp",round(row["after_tax_immediate_delta_vs_frozen_pp"],3))
    else:
        print("TAX_BLOCKER="+outcome["reason"])


if __name__=="__main__":
    main()

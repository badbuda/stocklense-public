"""SL-51 research-only turnover/tax experiment for frozen 8.0 target weights.

Input is a chronological *point-in-time* list of supplied 09:31, 09:32 and
closing quotes, FX, and PRIOR-session signals. Never downloads prices, writes
broker orders, mutates ST/PROD or changes frozen strategy code.
"""
import argparse
import json
import math
from pathlib import Path

from paper_rebalance_math import target_shares, within_band
from stocklens.core import weights_for_leverage
from stocklens.tax_research import TaxBook

SYMBOLS = ("QQQ", "TQQQ")
FRACTION = 0.985
FEE = 0.0002
SLIP = 0.001


def target(level):
    q, t = weights_for_leverage(float(level))
    return {"QQQ": q * FRACTION, "TQQQ": t * FRACTION}


def replay(events, no_change_band=0.005, immediate_tax_withholding=False):
    """Taxes are a configurable counterfactual, not observed broker withholding."""
    if not events:
        raise ValueError("EMPTY_SCENARIOS")
    cash = 100000.0
    shares = {s: 0 for s in SYMBOLS}
    taxes = TaxBook()
    counts = {"BUY": 0, "SELL": 0}
    turnover = fees = slippage = estimated_withheld_usd = 0.0
    ledger = []
    prev_day = ""
    peak = 100000.0
    maxdd = 0.0
    for e in events:
        day = e["date"]
        if day <= prev_day:
            raise ValueError("UNSORTED_OR_DUPLICATE_SESSION")
        prev_day = day
        w = target(e["leverage"])
        fx = float(e["fx_ils_per_usd"])
        if fx <= 0 or not math.isfinite(fx):
            raise ValueError("INVALID_FX")
        p31 = {s: float(e[s.lower()+"_0931"]) for s in SYMBOLS}
        p32 = {s: float(e[s.lower()+"_0932"]) for s in SYMBOLS}
        close = {s: float(e[s.lower()+"_close"]) for s in SYMBOLS}
        if any(not math.isfinite(px) or px <= 0 for px in (*p31.values(),*p32.values(),*close.values())):
            raise ValueError("INVALID_MARKET_PRICES")
        eq31 = cash + sum(shares[s]*p31[s] for s in SYMBOLS)
        action = e.get("action", "REBALANCE_NEXT_SESSION")
        if action not in ("NO_CHANGE", "REBALANCE_NEXT_SESSION", "ENTER_CASH_NEXT_SESSION", "EXIT_CASH_NEXT_SESSION"):
            raise ValueError("UNSUPPORTED_SIGNAL")
        skipped = action == "NO_CHANGE" and within_band(shares, w, p31, eq31, tolerance=no_change_band)
        daily = []
        if not skipped:
            desired = target_shares(w, eq31, p31)
            for s in SYMBOLS:
                qty = shares[s] - desired[s]
                if qty <= 0:
                    continue
                price = p31[s] * (1-SLIP)
                fee = qty * price * FEE
                result = taxes.sell(day, s, qty, price, fee, fx)
                cash += qty*price-fee
                shares[s] -= qty
                tax_usd = float(result["estimated_incremental_tax_ils"]) / fx
                if immediate_tax_withholding:
                    cash -= tax_usd
                    estimated_withheld_usd += tax_usd
                turnover += qty*p31[s]
                fees += fee
                slippage += qty*p31[s]*SLIP
                counts["SELL"] += 1
                daily.append({"symbol":s,"side":"SELL","qty":qty,"tax_scenario_usd":tax_usd})
            eq32 = cash + sum(shares[s]*p32[s] for s in SYMBOLS)
            desired32 = target_shares(w, eq32, p32)
            for s in SYMBOLS:
                requested = max(0, desired32[s]-shares[s])
                price = p32[s]*(1+SLIP)
                qty = min(requested, math.floor((cash+1e-8)/(price*(1+FEE))))
                if qty <= 0:
                    continue
                fee = qty*price*FEE
                cash -= qty*price+fee
                shares[s] += qty
                taxes.buy(day,s,qty,price,fee,fx)
                turnover += qty*p32[s]
                fees += fee
                slippage += qty*p32[s]*SLIP
                counts["BUY"] += 1
                daily.append({"symbol":s,"side":"BUY","qty":qty})
        if cash < -1e-6 or any(v < 0 for v in shares.values()):
            raise ValueError("INVALID_PORTFOLIO_CASH_SHARES")
        if any(taxes.quantity(s)!=shares[s] for s in SYMBOLS):
            raise ValueError("FIFO_POSITION_MISMATCH")
        equity = cash+sum(shares[s]*close[s] for s in SYMBOLS)
        peak = max(equity, peak)
        maxdd = min(maxdd, equity/peak-1)
        ledger.append({"date":day,"action":action,"skipped":skipped,
                       "equity_usd":round(equity,4),"shares":dict(shares),
                       "cash_usd":round(cash,4),"trades":daily})
    return {"model":"RESEARCH_NOT_LIVE","scenario":{"no_change_band":no_change_band,
             "immediate_tax_withholding":immediate_tax_withholding},
            "nav_usd":round(ledger[-1]["equity_usd"],4),
            "max_drawdown":round(maxdd,6),
            "total_turnover_usd":round(turnover,2),
            "fee_usd":round(fees,2),"slippage_usd":round(slippage,2),
            "estimated_tax_assessed_ils":taxes.summary()["tax_assessed_ils"],
            "estimated_withheld_usd":round(estimated_withheld_usd,4),
            "counts":counts,"ledger":ledger,"tax_book":taxes.summary(),
            "tax_events":taxes.events}


def monthly_broker_tax_projection(tax_events, rate=0.25):
    """Illustrative monthly settlement / within-year credit, not broker ledger.

    Uses taxable capital-gain scenarios only; excludes real FX debits and
    transaction cash feedback. Does not carry credits to a new year silently.
    """
    by_month = {}
    for event in tax_events:
        if event.get("side") != "SELL":
            continue
        month = event["date"][:7]
        row = by_month.setdefault(month, {"gain_ils":0.0, "loss_ils":0.0})
        row["gain_ils"] += float(event["eligible_gain_ils"])
        row["loss_ils"] += float(event["eligible_loss_ils"])
    prev_year = None
    ytd_net = ytd_paid = 0.0
    settlements = []
    for month in sorted(by_month):
        year = month[:4]
        if year != prev_year:
            prev_year, ytd_net, ytd_paid = year, 0.0, 0.0
        x = by_month[month]
        ytd_net += x["gain_ils"] - x["loss_ils"]
        liability = max(0.0, ytd_net) * float(rate)
        delta = liability - ytd_paid
        ytd_paid += delta
        settlements.append({"month":month,"estimated_settlement_ils":round(delta,2),
                            "gain_ils":round(x["gain_ils"],2),
                            "loss_ils":round(x["loss_ils"],2),
                            "year_to_date_liability_ils":round(ytd_paid,2)})
    return {"model":"EXCELLENCE_MONTHLY_NETTING_PROJECTION_NOT_ACTUAL_WITHHOLDING",
            "settlements":settlements,
            "excluded":"FX_CONVERSION_OF_CASH_AND_BROKER_TIMING_NOT_REPLAYED"}


def compare(events):
    baseline = replay(events)
    return {"inputs":"MUST_BE_POINT_IN_TIME",
            "monthly_broker_tax_projection":monthly_broker_tax_projection(baseline["tax_events"]),
            "comparison":{
        "baseline_pre_tax":baseline,
        "baseline_with_immediate_tax_scenario":replay(events,immediate_tax_withholding=True),
        "wider_1pct_with_immediate_tax_scenario":replay(events,0.01,True),
        "wider_2pct_with_immediate_tax_scenario":replay(events,0.02,True),
    }}


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--input",required=True,help="Chronological JSON list of observed sessions and prior signals")
    p.add_argument("--output",required=True)
    args=p.parse_args()
    events=json.loads(Path(args.input).read_text())
    result=compare(events)
    Path(args.output).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("SL51_RESEARCH_ONLY:",args.output)


if __name__=="__main__":
    main()

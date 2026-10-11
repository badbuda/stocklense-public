"""Fixed, preregistered GLD/TLT diversification against immutable StockLens 8.0.

REAL observed QQQ/TQQQ/GLD/TLT adjusted daily opens/closes ONLY. Satellite
weights fixed before examining returns. No synthetic funds, leverage fabrication,
automatic promotion, broker order authority or pristine OOS inference.
"""
from __future__ import annotations
from datetime import date
from pathlib import Path
import json
import math

from observed_etf_two_question_audit import (
    load, START_CAPITAL, _metrics, _prices, _run as frozen_reference, SPLITS
)
from observed_etf_four_challengers_batch import simulate as fixed_frozen
from research_diversified_sleeve_contract import inspect as inspect_input
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION

SOURCE = Path("research/private/non_nasdaq_observed_etfs.json")
OUT = Path("research/results/observed_nonnasdaq_fixed_sleeves.json")
REPORT = Path("research/reports/observed_nonnasdaq_fixed_sleeves.md")
EXPECTED_BASE_SOURCE = "bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129"
EXPECTED_EXTERNAL_BARS = "2f680455c1ba81eb2e859eb9520efb2c1139d2e2861ba715c697712004ee2210"
MODES = {"frozen": (1.0, 0.0, 0.0),
         "frozen85_gld075_tlt075": (0.85, 0.075, 0.075),
         "frozen70_gld15_tlt15": (0.70, 0.15, 0.15)}
LAGS = (0, 1)
SLIPPAGES = (10., 20.)
FEE_BPS = 2.
SYMBOLS = ("QQQ", "TQQQ", "GLD", "TLT")


def validate_inputs(rows, source, *, attest_source=True):
    if not rows or not isinstance(source, dict):
        raise ValueError("SLEEVE_NO_INPUTS")
    if attest_source and source.get("requested_baseline_snapshot_sha256") != EXPECTED_BASE_SOURCE:
        raise ValueError("SLEEVE_ORIGINAL_ETF_SNAPSHOT_CHANGED")
    meta = inspect_input(rows, source)
    if attest_source and meta["source_data_sha256"] != EXPECTED_EXTERNAL_BARS:
        raise ValueError("SLEEVE_PRICE_SNAPSHOT_CHANGED")
    return meta


def _mark4(p, prices, field):
    return p["cash"] + sum(p["shares"][s]*prices[s][field] for s in SYMBOLS)


def _execute4(p, prices, weights, fee_bps, slip_bps):
    if set(weights) != set(SYMBOLS) or any(
        type(v) not in (float, int) or not math.isfinite(v) or v < 0
        for v in weights.values()
    ) or sum(weights.values()) > 1.0000000001:
        raise ValueError("SLEEVE_INVALID_WEIGHTS")
    equity = _mark4(p, prices, "open")
    if not math.isfinite(equity) or equity <= 0:
        raise ValueError("SLEEVE_INVALID_OPEN_NAV")
    targets = {s: math.floor(equity*weights[s]/prices[s]["open"]) for s in SYMBOLS}
    for s in SYMBOLS:
        excess = p["shares"][s]-targets[s]
        if excess > 0:
            ref = prices[s]["open"]
            fill = ref*(1-slip_bps/10000.)
            net = excess*fill*(1-fee_bps/10000.)
            p["cash"] += net
            p["shares"][s] -= excess
            p["trades"] += 1
    for s in SYMBOLS:
        missing = targets[s]-p["shares"][s]
        if missing > 0:
            ref = prices[s]["open"]
            fill = ref*(1+slip_bps/10000.)
            unit_cost = fill*(1+fee_bps/10000.)
            qty = min(missing,math.floor(max(0.,p["cash"])/unit_cost))
            if qty > 0:
                p["cash"] -= qty*unit_cost
                p["shares"][s] += qty
                p["trades"] += 1
    if p["cash"] < -1e-6:
        raise ValueError("SLEEVE_NEGATIVE_CASH")


def simulate(rows, source, *, mode="frozen", lag=0, slip_bps=10.,
             fee_bps=FEE_BPS, attest_source=True):
    if mode not in MODES or lag not in LAGS or slip_bps not in SLIPPAGES:
        raise ValueError("SLEEVE_UNREGISTERED_HYPOTHESIS")
    if not (type(fee_bps) in (float,int) and 0 <= fee_bps <= 50):
        raise ValueError("SLEEVE_UNREGISTERED_FEES")
    validate_inputs(rows, source, attest_source=attest_source)
    cash_portfolio={"cash":START_CAPITAL,"shares":{s:0 for s in SYMBOLS},
                    "trades":0}
    dates=[r["date"] for r in rows]
    navs=[]
    previous_target=None
    previous_year=None
    sleeve, gold, treasury=MODES[mode]
    by_symbol={s:{r["date"]:r for r in source["bars"][s]}
               for s in ("GLD","TLT")}
    for i,r in enumerate(rows):
        j=i-lag
        frozen_lev=rows[j]["l"] if j>=0 else 0
        if frozen_lev not in (0,1.25,2,3) or r.get("signal","")>=r["date"]:
            raise ValueError("SLEEVE_FROZEN_SIGNAL_UNVERIFIED")
        q,t=weights_for_leverage(frozen_lev) if frozen_lev else (0.,0.)
        weights={"QQQ":sleeve*TARGET_INVESTED_FRACTION*q,
                 "TQQQ":sleeve*TARGET_INVESTED_FRACTION*t,
                 "GLD":gold,"TLT":treasury}
        prices=_prices(r)
        prices.update({"GLD":{k:by_symbol["GLD"][r["date"]][k] for k in ("open","close")},
                       "TLT":{k:by_symbol["TLT"][r["date"]][k] for k in ("open","close")}})
        annual_reset=mode!="frozen" and previous_year!=r["date"][:4]
        if previous_target is None or frozen_lev!=previous_target or annual_reset:
            _execute4(cash_portfolio,prices,weights,fee_bps,slip_bps)
        nav=_mark4(cash_portfolio,prices,"close")
        if not math.isfinite(nav) or nav<=0 or cash_portfolio["cash"] < -1e-5:
            raise ValueError("SLEEVE_INVALID_CLOSE_NAV")
        navs.append(nav)
        previous_target=frozen_lev
        previous_year=r["date"][:4]
    return {"stats":_metrics(navs,dates),"dates":dates,"navs":navs,
            "trades":cash_portfolio["trades"],"no_synthetic_etfs":True,
            "broker_fills_verified":False,"actual_broker_cash_yield_modeled":False}


def era(path, start, end):
    ix=[i for i,d in enumerate(path["dates"]) if start<=d<=end]
    if not ix: raise ValueError("SLEEVE_ERA_MISSING")
    a,b=ix[0],ix[-1]
    previous=START_CAPITAL if a==0 else path["navs"][a-1]
    return _metrics(path["navs"][a:b+1],path["dates"][a:b+1],first=previous)


def evaluate(market, source):
    rows=market["daily"]
    meta=validate_inputs(rows,source)
    if market.get("snapshot_sha256")!=EXPECTED_BASE_SOURCE:
        raise ValueError("SLEEVE_QQQ_TQQQ_REPLAY_SOURCE_CHANGED")
    all_runs={(m,l,s):simulate(rows,source,mode=m,lag=l,slip_bps=s)
              for m in MODES for l in LAGS for s in SLIPPAGES}
    for lag in LAGS:
        for slip in SLIPPAGES:
            main=all_runs[("frozen",lag,slip)]
            reference=fixed_frozen(rows,mode="frozen",lag=lag,slippage_bps=slip)
            if any(abs(a-b)>1e-5 for a,b in zip(main["navs"],reference["navs"])):
                raise ValueError("SLEEVE_FROZEN_NAV_PARITY_BROKEN")
    reference=all_runs[("frozen",0,10.)]["stats"]
    comparisons={}
    for m in MODES:
        a=all_runs[(m,0,10.)]["stats"]
        if m=="frozen":
            continue
        scenarios=[]
        for lag in LAGS:
            for slip in SLIPPAGES:
                x=all_runs[(m,lag,slip)]["stats"]
                b=all_runs[("frozen",lag,slip)]["stats"]
                scenarios.append({"lag":lag,"slippage_bps_per_side":slip,
                  "cagr_delta_pp":100*(x["cagr"]-b["cagr"]),
                  "maxdd_gain_pp":100*(x["max_drawdown"]-b["max_drawdown"]),
                  "passes_screen":(x["max_drawdown"]-b["max_drawdown"]>=.03
                                   and x["cagr"]-b["cagr"]>=-.015)})
        comparisons[m]={"cagr":a["cagr"],"max_drawdown":a["max_drawdown"],
          "cagr_delta_pp":100*(a["cagr"]-reference["cagr"]),
          "maxdd_gain_pp":100*(a["max_drawdown"]-reference["max_drawdown"]),
          "trades":all_runs[(m,0,10.)]["trades"],
          "cost_lag_scenarios":scenarios,
          "continuation_cases_passed":sum(x["passes_screen"] for x in scenarios),
          "continuation_required":4,
          "historical_research_continue_only":all(x["passes_screen"] for x in scenarios),
          "eras":{k:{"cagr_delta_pp":100*(era(all_runs[(m,0,10.)],start,end)["cagr"]
                                          -era(all_runs[("frozen",0,10.)],start,end)["cagr"]),
                      "maxdd_gain_pp":100*(era(all_runs[(m,0,10.)],start,end)["max_drawdown"]
                                          -era(all_runs[("frozen",0,10.)],start,end)["max_drawdown"])}
                  for k,(start,end) in SPLITS.items()}}
    return {"schema_version":1,
            "kind":"PREREGISTERED_OBSERVED_ETF_NONNASDAQ_SLEEVE_RESEARCH",
            "sample_sessions":len(rows),"start":rows[0]["date"],"end":rows[-1]["date"],
            "source_data_sha256":meta["source_data_sha256"],
            "qqq_tqqq_source_sha256":market["snapshot_sha256"],
            "frozen_reference":reference,
            "frozen_trades":all_runs[("frozen",0,10.)]["trades"],
            "baseline_day_by_day_parity":True,
            "comparisons":comparisons,
            "reused_historical_sample_not_clean_oos":True,
            "external_etf_price_source_independently_audited":False,
            "execution_pricing":"REAL_ADJUSTED_DAILY_OPEN_PROXY_NOT_NBBO",
            "annual_rebalance":True,
            "no_contributions":True,"no_synthetic_etf_returns":True,
            "frozen_stocklens8_changed":False,"capital_deployment_authorized":False,
            "automatic_promotion":False}


def build():
    market=load()
    if not SOURCE.exists():
        raise ValueError("SLEEVE_SOURCE_ARTIFACT_MISSING")
    source=json.loads(SOURCE.read_text())
    result=evaluate(market,source)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    lines=["# SL9-013: fixed observed GLD/TLT sleeves, reused sample",
           "", "Research only. Historical ETF Yahoo adjusted daily opens, no NBBO.",
           "Frozen 8.0 identical NAV path in all matched lag/cost scenarios.",
           "No independent ETF feed audit or new OOS sample; no capital promotion.",
           "", "| Mode | CAGR | MaxDD | CAGR delta pp | MaxDD gain pp | Trades | Gate |",
           "|---|---:|---:|---:|---:|---:|---:|"]
    b=result["frozen_reference"]
    lines.append(f'| frozen | {b["cagr"]:.2%} | {b["max_drawdown"]:.2%} | 0 | 0 | {result["frozen_trades"]} | baseline |')
    for m,v in result["comparisons"].items():
        lines.append(f'| {m} | {v["cagr"]:.2%} | {v["max_drawdown"]:.2%} | {v["cagr_delta_pp"]:+.2f} | {v["maxdd_gain_pp"]:+.2f} | {v["trades"]} | {v["continuation_cases_passed"]}/4 |')
    lines += ["","Weights fixed beforehand: frozen 85% + GLD 7.5% + TLT 7.5%; "
              "or frozen 70% + GLD 15% + TLT 15%. Rebalance yearly and when frozen "
              "signal changes. Total capital $100k, no contributions, 2bps fee "
              "and 10bps baseline slippage per trade side, additional lag/slippage stress.",
              "", "Every included ETF price actually observed (not synthetic), but "
              "Yahoo price-adjustment and actual execution are not independently audited. "
              "No strategy change, broker trade or model promotion."]
    REPORT.write_text("\n".join(lines)+"\n")
    short={"source_sha256":result["source_data_sha256"],
           "base":{k:result["frozen_reference"][k]
                    for k in ("cagr","max_drawdown")},
           "candidates":{m:{k:v[k] for k in ("cagr","max_drawdown",
                  "cagr_delta_pp","maxdd_gain_pp","continuation_cases_passed")}
                    for m,v in result["comparisons"].items()},
           "frozen_nav_parity":True,"promotion":False}
    print("STOCKLENS_FIXED_SLEEVE_RESULT="+json.dumps(short,sort_keys=True))
    return result


if __name__=="__main__":
    build()

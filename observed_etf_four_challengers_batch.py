"""Four frozen-vs-challenger families on observed real QQQ/TQQQ adjusted opens.

Research ONLY. Not a strategy modification, intraday execution, validated
held-out improvement, margin trade, or broker instruction. Uses existing
audited stocklens levels, independent whole-share simulated portfolios.
"""
from __future__ import annotations

from datetime import date
import json
import math
from pathlib import Path

from observed_etf_two_question_audit import (
    START_CAPITAL, SPLITS, _metrics, _prices, _run as frozen_reference, load
)
from stocklens.core import TARGET_INVESTED_FRACTION, weights_for_leverage
from tradable_tqqq_execution_comparison import _mark, _rebalance

MODES = ("frozen", "cap_2x", "cap_2_5x", "staged_up_3", "staged_both_3",
         "ewma5_shock")
CHALLENGERS = MODES[1:]
LAGS = (0, 1)
SLIPPAGES_BPS = (10., 20.)
FEE_BPS = 2.
CASH_RATE_SCENARIOS = (0., .02, .04)
OUT = Path("research/results/four_challengers_cash_and_event_samples.json")
REPORT = Path("research/reports/four_challengers_cash_and_event_samples.md")


def _ewma_caps(rows):
    """EWMA of already FINISHED daily QQQ log changes. At open i use cap[i-1]."""
    closes = [float(x["qc"]) for x in rows]
    caps = [3.] * len(rows)
    v = None
    alpha = 2. / (5. + 1.)
    for i in range(1, len(rows)):
        r = math.log(closes[i] / closes[i-1])
        v = r*r if v is None else alpha*r*r+(1-alpha)*v
        if i >= 20:
            vol = math.sqrt(v*252.)
            cap = min(3., max(1., .60/max(vol, 1e-12)))
            if closes[i]/closes[i-1]-1 <= -.04:
                cap = min(cap, 1.25)
            if i>=3 and closes[i]/closes[i-3]-1 <= -.08:
                cap = min(cap, 1.25)
            caps[i] = cap
    return caps


def _stage(previous, desired, elapsed, anchor, variant):
    if variant not in ("staged_up_3", "staged_both_3"):
        return desired
    # Frozen defense is inviolable, including exit-to-cash. From 0x defense,
    # restore the frozen signal directly; do not invent a sub-1x allocation.
    if desired == 0. or previous == 0. or anchor == 0.:
        return desired
    if variant == "staged_up_3" and desired < anchor:
        return desired
    return anchor + (desired-anchor)*min(3,elapsed)/3.


def simulate(rows, *, mode="frozen", lag=0, slippage_bps=10.,
             fee_bps=FEE_BPS, annual_cash_yield=0.):
    if mode not in MODES or lag not in LAGS or slippage_bps not in SLIPPAGES_BPS:
        raise ValueError("UNDECLARED_MODE_OR_STRESS")
    if annual_cash_yield not in CASH_RATE_SCENARIOS:
        raise ValueError("UNDECLARED_CASH_RATE")
    if not rows:
        raise ValueError("NO_OBSERVED_BARS")
    dates = [x["date"] for x in rows]
    if dates != sorted(set(dates)):
        raise ValueError("UNSORTED_OR_DUPLICATE_DATES")
    for r in rows:
        if r.get("signal", "") >= r["date"] or r.get("l") not in (0,1.25,2,3):
            raise ValueError("LOOKAHEAD_OR_INVALID_FROZEN_SIGNAL")
        if not all(isinstance(r.get(k),(float,int)) and math.isfinite(r[k])
                   and r[k]>0 for k in ("qo","qc","to","tc")):
            raise ValueError("NOT_REAL_VALID_ETF_OHLC")
    caps = _ewma_caps(rows) if mode == "ewma5_shock" else None
    p = {"cash":START_CAPITAL,"shares":{"QQQ":0,"TQQQ":0},
         "fees":0.,"slippage":0.,"trades":0,"turnover_notional":0.}
    navs, levels = [], []
    previous_target = None
    previous_desired = None
    anchor = 0.
    elapsed = 0
    gross_cash_interest = 0.
    last_day = None
    for i,r in enumerate(rows):
        today = date.fromisoformat(r["date"])
        if last_day is not None and annual_cash_yield:
            days = (today-last_day).days
            if days <= 0: raise ValueError("INVALID_CALENDAR")
            gain = p["cash"]*((1+annual_cash_yield)**(days/365.2425)-1.)
            p["cash"] += gain
            gross_cash_interest += gain
        last_day = today
        j = i-lag
        desired = float(rows[j]["l"]) if j >= 0 else 0.
        if mode == "cap_2x": desired = min(desired,2.)
        elif mode == "cap_2_5x": desired = min(desired,2.5)
        elif mode == "ewma5_shock" and j > 0:
            desired = min(desired,caps[j-1])  # only PREVIOUS completed close
        if desired != previous_desired:
            anchor = previous_target if previous_target is not None else desired
            elapsed = 0
            previous_desired = desired
        elapsed += 1
        target = _stage(previous_target, desired, elapsed, anchor, mode)
        if target < 0 or target > 3 or (mode=="ewma5_shock" and target>float(rows[j]["l"])+1e-9):
            raise ValueError("INCOMPATIBLE_OVERLAY")
        if target == 0.:
            weights={"QQQ":0.,"TQQQ":0.}
        else:
            q,t=weights_for_leverage(target)
            weights={"QQQ":q*TARGET_INVESTED_FRACTION,
                     "TQQQ":t*TARGET_INVESTED_FRACTION}
        prices=_prices(r)
        if previous_target is None or abs(target-previous_target)>1e-10:
            _rebalance(p,prices,weights,fee_bps,slippage_bps)
        nav = _mark(p,prices,"close")
        if nav <= 0 or not math.isfinite(nav) or p["cash"] < -1e-5:
            raise ValueError("INVALID_PORTFOLIO_NAV")
        navs.append(nav)
        levels.append(target)
        previous_target=target
    return {"stats":_metrics(navs,dates),"navs":navs,"dates":dates,
            "levels":levels,"trades":p["trades"],"total_fees":p["fees"],
            "total_slippage":p["slippage"],"cash_interest":gross_cash_interest}


def _era(path, first, last):
    ids=[i for i,d in enumerate(path["dates"]) if first<=d<=last]
    if not ids: raise ValueError("MISSING_ERA")
    a,b=ids[0],ids[-1]
    prev=START_CAPITAL if a==0 else path["navs"][a-1]
    return _metrics(path["navs"][a:b+1],path["dates"][a:b+1],first=prev)


def evaluate(raw):
    rows=raw["daily"]
    base=simulate(rows)
    # Exact day-by-day replay parity before evaluating ANY challenger outcome.
    reference=frozen_reference(rows,variant="frozen",lag=0,
                               fee_bps=FEE_BPS,slip_bps=10.)
    if (len(base["navs"])!=len(reference["navs"]) or
        any(abs(a-b)>1e-5 for a,b in zip(base["navs"],reference["navs"]))):
        raise ValueError("FROZEN_BASELINE_DAILY_LEDGER_DIVERGENCE")
    all_runs={}
    for lag in LAGS:
        for slip in SLIPPAGES_BPS:
            for mode in MODES:
                all_runs[(mode,lag,slip)]=simulate(
                    rows,mode=mode,lag=lag,slippage_bps=slip)
    main = all_runs[("frozen",0,10.)]
    full={}
    for mode in MODES:
        run=all_runs[(mode,0,10.)]
        a=run["stats"]
        full[mode]={**a,
            "cagr_delta_pp":100*(a["cagr"]-main["stats"]["cagr"]),
            "maxdd_improvement_pp":100*(a["max_drawdown"]-main["stats"]["max_drawdown"]),
            "ending_wealth_ratio":a["ending_equity"]/main["stats"]["ending_equity"],
            "trade_count":run["trades"]}
    checks={}
    for mode in CHALLENGERS:
        cases=[]
        for lag in LAGS:
            for slip in SLIPPAGES_BPS:
                x=all_runs[(mode,lag,slip)]["stats"]
                y=all_runs[("frozen",lag,slip)]["stats"]
                cases.append({
                    "lag":lag,"slip_bps":slip,
                    "cagr_delta_pp":100*(x["cagr"]-y["cagr"]),
                    "maxdd_improvement_pp":100*(x["max_drawdown"]-y["max_drawdown"]),
                    "passes_conservative_screen":(
                        x["max_drawdown"]-y["max_drawdown"]>=.03
                        and x["cagr"]-y["cagr"]>=-.015)})
        checks[mode]={"passed":sum(x["passes_conservative_screen"] for x in cases),
                      "required":4,"cases":cases,
                      "research_continue_only":all(x["passes_conservative_screen"] for x in cases),
                      "automatic_promotion":False}
    era_results={}
    for name,(first,last) in SPLITS.items():
        base_era=_era(main,first,last)
        era_results[name]={}
        for mode in MODES:
            x=_era(all_runs[(mode,0,10.)],first,last)
            era_results[name][mode]={
                "cagr_delta_pp":100*(x["cagr"]-base_era["cagr"]),
                "maxdd_improvement_pp":100*(x["max_drawdown"]-base_era["max_drawdown"])}
    carry={}
    for rate in CASH_RATE_SCENARIOS:
        v=simulate(rows,annual_cash_yield=rate)["stats"]
        carry[str(rate)]={
            "counterfactual_fixed_rate_all_years":rate,
            "cagr":v["cagr"],"max_drawdown":v["max_drawdown"],
            "cagr_delta_pp":100*(v["cagr"]-main["stats"]["cagr"])}
    return {
        "schema_version":1,
        "kind":"OBSERVED_ETF_FOUR_HYPOTHESIS_BATCH_AND_CASH_SCENARIOS",
        "period":raw["period"],
        "source_snapshot_sha256":raw.get("snapshot_sha256"),
        "frozen_daily_ledger_parity":True,
        "predeclared_multiplicity":len(CHALLENGERS),
        "sample_is_pristine_out_of_sample":False,
        "genuine_broker_fills":False,
        "actual_historical_cash_rates_implemented":False,
        "synthetic_TQQQ_returns_used":False,
        "frozen_stocklens8_changed":False,
        "capital_deployment_authorized":False,
        "automatic_promotion":False,
        "full_period":full,"reused_eras":era_results,
        "cost_lag_gates":checks,"cash_carry_counterfactual":carry
    }


def human_report(report):
    out=["# Four challenger families — fixed pre-registration, research only",
         "",
         "Real observed Yahoo-adjusted QQQ/TQQQ open/close, 2 bps fee + 10 bps",
         "slippage each side; 0/1 additional decision lag, 10/20bps spread stress.",
         "Original frozen 8.0 decision rules not altered. Simulated DAILY opens",
         "are not 09:31 market executions or broker fills.",
         "",
         "| Mode | CAGR | MaxDD | delta CAGR (pp) | MaxDD benefit (pp) | trades | gate |",
         "|---|---:|---:|---:|---:|---:|---|"]
    for mode in MODES:
        v=report["full_period"][mode]
        g=report["cost_lag_gates"].get(mode,{})
        out.append(f'| {mode} | {v["cagr"]:.2%} | {v["max_drawdown"]:.2%} | '
                   f'{v["cagr_delta_pp"]:+.2f} | {v["maxdd_improvement_pp"]:+.2f} | '
                   f'{v["trade_count"]} | {g.get("passed", "-")}/4 |')
    out+=["","## Fixed-rate cash carry counterfactual (NOT real historical rates)",""]
    for rate,x in report["cash_carry_counterfactual"].items():
        out.append(f'- Constant annual cash yield {float(rate):.0%}: '
                   f'CAGR={x["cagr"]:.2%}; delta={x["cagr_delta_pp"]:+.3f}pp.')
    out+=["","## No model promotion","",
          "Pass a historical continuation screen only if ALL four 0/1-session",
          "lag × 10/20bps slippage combinations improve MaxDD by >=3pp",
          "while reducing CAGR by no more than 1.5pp. This is NOT a fresh",
          "out-of-sample test: all decades have already been repeatedly inspected.",
          "Constant 2%/4% cash yields are illustrative, not historical broker rates.",
          "FOMC/CPI archival calendars remain descriptive and do not imply",
          "known decision outcomes, timestamp-certified first-seen headlines,",
          "historical news alpha, or any capital authorization.",
          ""]
    return "\n".join(out)


def build(out=OUT, report=REPORT):
    result=evaluate(load())
    out.parent.mkdir(parents=True,exist_ok=True)
    report.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    report.write_text(human_report(result))
    print("FOUR_CHALLENGERS_RESULT="+json.dumps({
        "period":result["period"],"full":{k:{
            "cagr":v["cagr"],"maxdd":v["max_drawdown"],
            "cagr_delta_pp":v["cagr_delta_pp"],
            "dd_gain_pp":v["maxdd_improvement_pp"]}
            for k,v in result["full_period"].items()},
        "gates":{k:v["passed"] for k,v in result["cost_lag_gates"].items()},
        "cash":result["cash_carry_counterfactual"],
        "frozen_parity":result["frozen_daily_ledger_parity"],
        "promotion":False},sort_keys=True))
    return result


if __name__=="__main__":
    build()

"""Predeclared attribution of already-falsified fixed GLD/TLT sleeves.

DESCRIPTIVE only: no additional candidate allocation or weight optimization.
Uses same pinned observed data and frozen whole-share NAV simulator as SL9-013.
"""
from __future__ import annotations
from pathlib import Path
import json
import math

from observed_etf_two_question_audit import load
from observed_nonnasdaq_sleeve_study import SOURCE, MODES, validate_inputs, simulate

OUT=Path("research/results/fixed_sleeve_crisis_diagnostics.json")
REPORT=Path("research/reports/fixed_sleeve_crisis_diagnostics.md")
CRISES={
    "2015_2016_peak_to_trough":("2015-07-20","2016-06-27"),
    "covid_peak_to_trough":("2020-02-19","2020-03-16"),
    "2022_peak_to_trough":("2021-11-19","2022-05-06"),
    "2018_q4":("2018-10-01","2019-01-02"),
}
YEARS={
    "2010_2017":("2010-02-11","2017-12-29"),
    "2018_2022":("2018-01-02","2022-12-30"),
    "2023_2026":("2023-01-03","2026-10-09"),
}


def _between(start,end,date_values):
    ix=[i for i,d in enumerate(date_values) if start<=d<=end]
    if not ix:
        raise ValueError("DIAGNOSTICS_PREDECLARED_WINDOW_UNOBSERVED")
    return ix[0],ix[-1]


def _peak_to_trough(path):
    high=path[0]
    maxdd=0.0
    high_ix=low_ix=0
    most_high=0
    for i,nav in enumerate(path):
        if nav>high:
            high=nav
            most_high=i
        depth=nav/high-1.
        if depth<maxdd:
            maxdd=depth
            high_ix=most_high
            low_ix=i
    return maxdd,high_ix,low_ix


def _case_series(path,first,last):
    a,b=_between(first,last,path["dates"])
    start,end=path["navs"][a],path["navs"][b]
    if start <= 0 or end <= 0:
        raise ValueError("DIAGNOSTICS_NONPOSITIVE_NAV")
    worst,ixh,ixl=_peak_to_trough(path["navs"][a:b+1])
    return {"start_session":path["dates"][a],"end_session":path["dates"][b],
       "endpoint_close_to_close_return":end/start-1,
       "local_window_max_drawdown":worst,
       "local_peak_session":path["dates"][a+ixh],
       "local_trough_session":path["dates"][a+ixl],
       "endpoint_metric_not_independently_published_fund_return":True}


def _worst_daily(path):
    navs=path["navs"]
    vals=[navs[i]/navs[i-1]-1 for i in range(1,len(navs))]
    i=min(range(len(vals)), key=lambda j: vals[j])
    return {"return":vals[i],"session":path["dates"][i+1]}


def evaluate(market,source):
    rows=market["daily"]
    validate_inputs(rows,source)
    p={mode:simulate(rows,source,mode=mode,lag=0,slip_bps=10.) for mode in MODES}
    result={
        "schema_version":1,"kind":"FIXED_REAL_ETF_SLEEVE_CRISIS_FALSIFICATION_ONLY",
        "source_snapshot_sha256":market["snapshot_sha256"],
        "real_prices_no_synthetic_etf":True,
        "period":market["period"],
        "crisis_windows":{},
        "market_eras":{},
        "full_path_worst_daily":{},
        "full_path_peak_to_trough":{},
        "no_new_hypothesis_tuning":True,
        "pristine_out_of_sample":False,
        "source_independently_audited":False,
        "broker_fills_verified":False,
        "frozen8_changed":False,
        "automatic_promotion":False,
        "capital_deployment_authorized":False,
    }
    for name,(start,end) in CRISES.items():
        result["crisis_windows"][name]={mode:_case_series(p[mode],start,end) for mode in MODES}
    for name,(start,end) in YEARS.items():
        result["market_eras"][name]={mode:_case_series(p[mode],start,end) for mode in MODES}
    for mode in MODES:
        result["full_path_worst_daily"][mode]=_worst_daily(p[mode])
        depth,h,l=_peak_to_trough(p[mode]["navs"])
        result["full_path_peak_to_trough"][mode]={
            "drawdown":depth,"high_session":p[mode]["dates"][h],
            "low_session":p[mode]["dates"][l],
            "trades":p[mode]["trades"],
        }
    return result


def build():
    if not SOURCE.exists():
        raise ValueError("DIAGNOSTICS_OBSERVED_SOURCE_ARCHIVE_REQUIRED")
    m=load()
    o=evaluate(m,json.loads(SOURCE.read_text(encoding="utf-8")))
    OUT.parent.mkdir(parents=True,exist_ok=True)
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(o,indent=2,sort_keys=True)+"\n")
    lines=["# SL9-014 — already preregistered GLD/TLT sleeve stress diagnostics","",
      "Existing fixed weights, 2010–2026 Yahoo-adjusted observed ETF daily",
      "OPEN execution proxy, no independent 09:31 fills or untouched OOS.",
      "No weights or thresholds tuned after outcomes.","",
      "| Window | Frozen close-to-close | 85/7.5/7.5 | 70/15/15 |",
      "|---|---:|---:|---:|"]
    for name,cases in o["crisis_windows"].items():
        values=[cases[m]["endpoint_close_to_close_return"] for m in MODES]
        lines.append(f'| {name} | {values[0]:+.2%} | {values[1]:+.2%} | {values[2]:+.2%} |')
    lines.extend(["","Crisis windows reflect *close-to-close endpoint returns*, not",
                  "necessarily portfolio-specific full peak-to-trough drawdowns.",
                  "No source-audited ETF adjustments or real brokerage quotes.",
                  "StockLens 8.0 remains unchanged and no strategy is promoted."])
    REPORT.write_text("\n".join(lines)+"\n")
    print("STOCKLENS_SLEEVE_CRISIS="+json.dumps({
        "crisis_endpoint_returns":{w:{m:round(k["endpoint_close_to_close_return"],6)
          for m,k in c.items()} for w,c in o["crisis_windows"].items()},
        "worst_day":o["full_path_worst_daily"],
        "peak_to_trough":o["full_path_peak_to_trough"],
        "no_promotion":True,
    },sort_keys=True))
    return o


if __name__=="__main__":
    build()

"""Forensic *cross-provider* SL724 LEAN vs Yahoo ETF proxy exposure comparison.

DO NOT use this to certify original LEAN features, identical input, fills,
alpha, or order parity. The proxy uses PREVIOUS-session signals and observed
Yahoo ETF daily opens, not the same decision timestamp as LEAN charts.
This tool diagnoses day-by-day disagreement instead of the misleading
transition-index rate, with an explicit trading-session lag profile.
"""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from datetime import date
from pathlib import Path

from qc_original_lean_chart_audit import extract
from json_artifacts import write_json_atomic

LEV=(0.0, 1.25, 2.0, 3.0)
LAGS=(-2, -1, 0, 1, 2)


def diagnose(original, proxy_rows):
    if not original:
        raise ValueError("EMPTY_ORIGINAL_REFERENCE")
    orig={}
    for row in original:
        day=date.fromisoformat(row["date"]).isoformat()
        lev=float(row["leverage"])
        if day in orig or lev not in LEV:
            raise ValueError("INVALID_ORIGINAL_CHRONOLOGY_OR_LEVERAGE")
        orig[day]=lev
    if list(orig)!=sorted(orig):
        raise ValueError("UNSORTED_ORIGINAL_SESSIONS")
    proxy={}
    prev_date=None
    for row in proxy_rows:
        day=date.fromisoformat(row["date"]).isoformat()
        if prev_date and day<=prev_date:
            raise ValueError("DUPLICATE_OR_UNSORTED_PROXY_SESSIONS")
        if row.get("signal") and not row["signal"]<day:
            raise ValueError("PROXY_SIGNAL_NOT_PRIOR_TO_EXECUTION")
        lev=float(row["l"])
        if not math.isfinite(lev) or lev not in LEV:
            raise ValueError("INVALID_PROXY_EXPOSURE")
        proxy[day]=lev
        prev_date=day
    proxy_dates=list(proxy)
    pindex={d:i for i,d in enumerate(proxy_dates)}
    common=[d for d in orig if d in pindex]
    if not common:
        raise ValueError("NO_OVERLAPPING_SESSIONS")
    confusion=Counter()
    per_year={}
    mismatches=[]
    episodes=[]
    active=None
    previous_proxy_index=None
    for day in common:
        lean=orig[day];p=proxy[day]
        year=day[:4]
        bucket=per_year.setdefault(year,{"overlap_sessions":0,"matching_sessions":0,"absolute_leverage_gap":0.0})
        bucket["overlap_sessions"]+=1
        bucket["matching_sessions"]+=int(lean==p)
        bucket["absolute_leverage_gap"]+=abs(lean-p)
        confusion[(lean,p)]+=1
        idx=pindex[day]
        if lean!=p:
            if active and previous_proxy_index==idx-1:
                active["end_date"]=day
                active["sessions"]+=1
            else:
                if active: episodes.append(active)
                active={"start_date":day,"end_date":day,"sessions":1,
                        "original_leverage_at_start":lean,"yahoo_proxy_exposure_at_start":p}
            if len(mismatches)<30:
                mismatches.append({"date":day,"original_lean_leverage":lean,
                                   "yahoo_prior_signal_execution_leverage":p,
                                   "absolute_gap":abs(lean-p)})
        elif active:
            episodes.append(active);active=None
        previous_proxy_index=idx
    if active: episodes.append(active)
    for y,b in per_year.items():
        b["match_rate"]=b["matching_sessions"]/b["overlap_sessions"]
        b["average_absolute_leverage_gap"]=b.pop("absolute_leverage_gap")/b["overlap_sessions"]
    profile=[]
    for shift in LAGS:
        n=match=0
        for day in common:
            j=pindex[day]+shift
            if not 0<=j<len(proxy_dates):continue
            match+=int(orig[day]==proxy[proxy_dates[j]])
            n+=1
        profile.append({"offset_in_yahoo_exchange_sessions":shift,
                        "compared_sessions":n,"matching_sessions":match,
                        "match_rate":match/n if n else None})
    baseline=next(x for x in profile if x["offset_in_yahoo_exchange_sessions"]==0)
    best=max(profile,key=lambda x:x["match_rate"] if x["match_rate"] is not None else -1)
    missing_original=len(orig)-len(common)
    missing_proxy=len(proxy)-len(common)
    return {
        "status":"CROSS_PROVIDER_LEVERAGE_DIAGNOSTIC_ONLY",
        "kind":"LEAN_SL724_VS_YAHOO_PRIOR_SIGNAL_EXECUTION_PROXY",
        "reference_sessions":len(orig),"proxy_sessions":len(proxy),
        "overlap_sessions":len(common),
        "overlap_first":common[0],"overlap_last":common[-1],
        "original_sessions_outside_proxy":missing_original,
        "proxy_sessions_outside_original":missing_proxy,
        "matching_exposure_sessions":baseline["matching_sessions"],
        "same_date_exposure_match_rate":baseline["match_rate"],
        "lag_profile":profile,
        "best_diagnostic_offset_in_yahoo_sessions":best["offset_in_yahoo_exchange_sessions"],
        "per_calendar_year":per_year,
        "confusion":[{"original_lean_leverage":k[0],
                      "yahoo_execution_proxy_leverage":k[1],"sessions":n}
                     for k,n in sorted(confusion.items())],
        "top_mismatch_episodes":sorted(episodes,key=lambda x:(-x["sessions"],x["start_date"]))[:15],
        "first_mismatched_days":mismatches,
        "same_input_parity_proven":False,
        "diagnostic_lag_not_model_adjustment":True,
        "critical_warning":"Do not interpret high same-date match as LEAN-vs-Python identity. Dominant persistent 3x exposure and prior-day Yahoo execution semantics can inflate equality, while original LEAN input is still missing.",
    }


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--original",required=True,help="Original private frozen SL724 QuantConnect results JSON")
    cli.add_argument("--proxy",default="docs/portal-history.json")
    cli.add_argument("--out",default="research/local/lean_yahoo_daily_exposure_diagnostic.json")
    args=cli.parse_args()
    original,audit=extract(args.original)
    obj=json.loads(Path(args.proxy).read_text(encoding="utf-8"))
    if obj.get("observed_ohlc_available") is not True:
        raise ValueError("PROXY_NOT_BASED_ON_OBSERVED_ETF_PRICES")
    result=diagnose(original,obj["daily"])
    result["original_source_sha256"]=audit["source_sha256"]
    result["proxy_evidence"]=obj.get("evidence")
    write_json_atomic(args.out,result)
    print(json.dumps({
        k:result[k] for k in ("status","reference_sessions","proxy_sessions",
                             "overlap_sessions","same_date_exposure_match_rate",
                             "lag_profile","best_diagnostic_offset_in_yahoo_sessions",
                             "same_input_parity_proven")},indent=2))


if __name__=="__main__":
    main()

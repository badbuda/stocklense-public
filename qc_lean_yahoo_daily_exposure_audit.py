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
    if not proxy_dates:
        raise ValueError("EMPTY_PROXY_SESSION_SET")
    orig_first=next(iter(orig))
    orig_last=next(reversed(orig))
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
    # Separate TQQQ pre-inception from actual missing exchange sessions.
    original_pre_proxy=sum(day<proxy_dates[0] for day in orig)
    original_post_proxy=sum(day>proxy_dates[-1] for day in orig)
    original_missing_within_proxy=missing_original-original_pre_proxy-original_post_proxy
    # Compare transitions as (date, leverage) pairs, not by event index;
    # initial Yahoo exposure is a baseline, never a transition.
    reference_changes=[]
    previous=None
    for day,lev in orig.items():
        if previous is None or lev!=previous:
            if proxy_dates[0]<=day<=proxy_dates[-1] and day!=proxy_dates[0]:
                reference_changes.append([day,lev])
            previous=lev
    proxy_changes=[]
    previous=None
    for day,lev in proxy.items():
        if previous is None or lev!=previous:
            if orig_first<=day<=orig_last and day!=proxy_dates[0]:
                proxy_changes.append([day,lev])
            previous=lev
    original_change_set={tuple(x) for x in reference_changes}
    proxy_change_set={tuple(x) for x in proxy_changes}
    observed_orig_non3=sum(orig[day]!=3.0 for day in common)
    matched_orig_non3=sum(orig[day]!=3.0 and orig[day]==proxy[day] for day in common)
    matched_3x=sum(orig[day]==3.0 and orig[day]==proxy[day] for day in common)
    orig_3x=sum(orig[day]==3.0 for day in common)
    denominators={
        "non_3x_reference_days": observed_orig_non3,
        "non_3x_matching_days": matched_orig_non3,
        "non_3x_match_rate": matched_orig_non3/observed_orig_non3 if observed_orig_non3 else None,
        "3x_reference_days": orig_3x,
        "3x_matching_days": matched_3x,
        "3x_match_rate": matched_3x/orig_3x if orig_3x else None,
    }
    missing_proxy=len(proxy)-len(common)
    return {
        "status":"CROSS_PROVIDER_LEVERAGE_DIAGNOSTIC_ONLY",
        "kind":"LEAN_SL724_VS_YAHOO_PRIOR_SIGNAL_EXECUTION_PROXY",
        "reference_sessions":len(orig),"proxy_sessions":len(proxy),
        "overlap_sessions":len(common),
        "overlap_first":common[0],"overlap_last":common[-1],
        "original_sessions_outside_proxy":missing_original,
        "proxy_sessions_outside_original":missing_proxy,
        "reference_before_yahoo_proxy_inception":original_pre_proxy,
        "reference_after_yahoo_proxy_end":original_post_proxy,
        "missing_reference_sessions_inside_yahoo_proxy_window":original_missing_within_proxy,
        "balanced_exposure_diagnostic":denominators,
        "transitions":{
            "reference_events_inside_proxy_period":len(reference_changes),
            "proxy_events_excluding_initial_baseline":len(proxy_changes),
            "exact_date_and_level_matches":len(original_change_set&proxy_change_set),
            "reference_events_not_in_proxy":[list(x) for x in reference_changes if tuple(x) not in proxy_change_set],
            "proxy_events_not_in_reference":[list(x) for x in proxy_changes if tuple(x) not in original_change_set],
            "scope":"EXACT_DATE_AND_LEVEL_PAIRS_NOT_TRANSITION_SEQUENCE_INDEX"
        },
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
        "critical_warning":"Even 99% cross-provider date-level exposure agreement cannot prove identical LEAN input features or alpha. This independently replays Yahoo QQQ completed closes but compares the original LEAN chart decision with a next-open Yahoo prior-close exposure; persistent 3x can inflate rates. Original native LEAN close/SMA/VOL/MOM values remain missing.",
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

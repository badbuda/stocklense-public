"""Leakage-safe, price-observed news event study; NO news-driven trades.

News events are supplied through a private first-seen-vetted journal. Event
TIME and availability must be known before first eligible NYSE opening.
If real vintage, publish and first-seen availability cannot be independently
verified, the event is EXCLUDED. Missing events => BLOCKED, never invented.

Event day 1/5/21 ETF Open->Close observed returns are RESEARCH LABELS,
not trading signals. Event clusters overlap; no iid p-values or auto-trading.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from statistics import median
import hashlib
import json
import math

import exchange_calendars as xcals

from news_event_pit import load_journal, utc, DEFAULT_JOURNAL
from observed_etf_two_question_audit import load as observed_prices
from json_artifacts import write_json_atomic

OUT = Path("research/results/news_pit_event_study.json")
REPORT = Path("research/reports/news_pit_event_study.md")
HORIZONS = (1, 5, 21)
MAX_DAILY_GAP = 0
SOURCE_PRICE_PATH = "docs/portal-history.json"


def eligible_market_open(event, *, calendar=None):
    """Map verified publication+provider-delivery+processing time to NYSE OPEN.

    This is an ASSUMED next-open execution proxy, not a LEAN 09:31 fill.
    """
    if not event.get("first_seen_proven"):
        raise ValueError("NEWS_NO_VERIFIED_POINT_IN_TIME_FIRST_SEEN")
    if event.get("event_kind")!="OUTCOME_RELEASED":
        raise ValueError("NEWS_FUTURE_SCHEDULE_NOT_OUTCOME")
    cal=calendar or xcals.get_calendar("XNYS")
    ready=utc(event["signal_ready_at_utc"],"signal_ready_at_utc")
    try:
        session=cal.date_to_session(ready.date().isoformat(),direction="next")
        if cal.session_open(session).to_pydatetime()<=ready:
            session=cal.next_session(session)
    except (ValueError,TypeError,OverflowError) as exc:
        raise ValueError("NEWS_NO_VERIFIABLE_NEXT_EXCHANGE_SESSION") from exc
    return str(session.date())


def _safe_ohlc(row):
    if not all(
        isinstance(row.get(k),(int,float)) and math.isfinite(row[k]) and row[k]>0
        for k in ("qo","qc","to","tc")
    ):
        raise ValueError("NEWS_OBSERVED_ETF_PRICES_INVALID")


def _returns(rows, start_i, horizon):
    end_i=start_i+horizon-1
    if end_i>=len(rows):return None
    start,end=rows[start_i],rows[end_i]
    for row in (start,end):_safe_ohlc(row)
    return {
        "horizon_sessions":horizon,
        "qqq_open_to_horizon_close_log_return":math.log(end["qc"]/start["qo"]),
        "tqqq_open_to_horizon_close_log_return":math.log(end["tc"]/start["to"]),
        "tqqq_minus_qqq_log_return":math.log(end["tc"]/start["to"])
                                      -math.log(end["qc"]/start["qo"]),
        "actual_etf_observations_not_broker_quotes":True,
    }


def study(rows, events):
    if not isinstance(rows,list) or len(rows)<10:
        raise ValueError("NEWS_NO_OBSERVED_ETF_HISTORY")
    by_day={}
    for i,row in enumerate(rows):
        day=row.get("date")
        if not isinstance(day,str) or day in by_day:
            raise ValueError("NEWS_DUPLICATE_ETF_DAY")
        _safe_ohlc(row)
        by_day[day]=i
    if list(by_day)!=sorted(by_day):
        raise ValueError("NEWS_UNSORTED_OBSERVED_ETF_HISTORY")
    if events.get("status") not in (
        "DATA_BLOCKED_NO_PIT_VERIFIED_EVENTS","HAS_PIT_ELIGIBLE_EVENTS"
    ):
        raise ValueError("NEWS_INVALID_EVENT_JOURNAL")
    cal=xcals.get_calendar("XNYS")
    grouped={}
    case_studies=[]
    blocked={
        "no_pit_event_evidence":events["raw_event_records"]
            -events["source_verified_records"],
        "out_of_observed_cohort":0,
        "no_observed_next_open_session":0,
        "missing_horizon_21":0,
    }
    for e in events["verified_distinct_events"]:
        day=eligible_market_open(e,calendar=cal)
        i=by_day.get(day)
        if i is None:
            if day<rows[0]["date"] or day>rows[-1]["date"]:
                blocked["out_of_observed_cohort"]+=1
            else:
                # Never silently fill a holiday, missing ETF quote or
                # absent observed session with the next available price.
                blocked["no_observed_next_open_session"]+=1
            continue
        out={"event_id":e["event_id"],"story":e["canonical_story_id"],
            "event_kind":e["event_kind"],"category":e["category"],"scope":e["scope"],
            "source_url":e["source_url"],"source_record_sha256":e["source_record_sha256"],
            "first_tradable_open_session":day,
            "signal_available_utc":e["signal_ready_at_utc"],
            "shadow_only_action":"NO_CHANGE",
            "frozen_target_unchanged":float(rows[i]["l"]),
            "market_reaction_not_prepublication_predictor":True}
        for horizon in HORIZONS:
            performance=_returns(rows,i,horizon)
            if performance:
                out["observed_horizon_"+str(horizon)]=performance
                key=(e["category"],horizon)
                grouped.setdefault(key,[]).append(
                    performance["tqqq_minus_qqq_log_return"])
            elif horizon==21:
                blocked["missing_horizon_21"]+=1
        case_studies.append(out)
    aggregated=[]
    for (category,horizon),values in sorted(grouped.items()):
        aggregated.append({
            "category":category,"horizon":horizon,"observed_event_count":len(values),
            "average_tqqq_minus_qqq_log_return":sum(values)/len(values),
            "median_tqqq_minus_qqq_log_return":median(values),
            "positive_relative_growth_fraction":sum(v>0 for v in values)/len(values),
            "independence_or_selection_corrected_significance_proven":False,
        })
    status=("HISTORICAL_NEWS_EVENT_STUDY_DESCRIPTIVE_ONLY" if case_studies
            else "BLOCKED_NO_GENUINE_TIMESTAMPED_HISTORICAL_EVENT_COHORT")
    return {
        "schema_version":1,
        "kind":"FROZEN8_PIT_NEWS_EVENTS_ONLY_DESCRIPTIVE",
        "status":status,"market_period":{"start":rows[0]["date"],
                                            "end":rows[-1]["date"],
                                            "sessions":len(rows)},
        "news_source_records":events["raw_event_records"],
        "verified_first_seen_distinct_news_events":events["distinct_verified_stories"],
        "actually_joined_eligible_market_events":len(case_studies),
        "blockers":blocked,
        "asof_method":"first NYSE open strictly after independently attested vendor first-seen plus provider delivery/processing lag and ten-minute buffer",
        "market_data":"ACTUAL_YAHOO_ADJUSTED_QQQ_TQQQ_DAILY_OPEN_CLOSE_NOT_MINUTE_QUOTE",
        "observed_reaction_horizons_sessions":list(HORIZONS),
        "category_attribution":aggregated,
        "event_cases":case_studies[:100],
        "event_cases_truncated":len(case_studies)>100,
        "event_journal_sha256":events["normalized_event_journal_sha256"],
        "historical_samples_untouched_holdout":False,
        "sponsor_news_transcript_text_copied":False,
        "original_8_0_changed":False,
        "event_based_model_prediction_proven":False,
        "causal_return_alpha_proven":False,
        "automatic_model_promotion":False,
        "capital_deployment_authorized":False,
        "real_broker_fills_verified":False,
        "risk_note":"Retrospective event association is NOT a deployable decision rule. GDELT 2.0 only from Feb 2015, provider coverage and historical 1st-seen can lag; no article revisions, user-shared headline or today's LLM output may be retrojected into market history."
    }


def build(journal=DEFAULT_JOURNAL,out=OUT,report=REPORT):
    market=observed_prices()
    events=load_journal(journal)
    result=study(market["daily"],events)
    result["market_source_snapshot_sha256"]=market.get("snapshot_sha256")
    result["user_archival_journal_present"]=Path(journal).exists()
    write_json_atomic(out,result)
    parts=[
        "# StockLens — news point-in-time historical readiness",
        "",
        "Status: **"+result["status"]+"**.",
        "No news-based live signal, capital deployment, broker fill, or frozen StockLens 8.0 strategy change.",
        "",
        "## Independent historical input evidence",
        "",
        "- Archived timestamped news records ingested: "+str(result["news_source_records"]),
        "- Independently attested distinct FIRST-SEEN stories: "+str(result["verified_first_seen_distinct_news_events"]),
        "- Stories causally mapped to an actually observed ETF session: "+str(result["actually_joined_eligible_market_events"]),
        "- Exact normalized journal SHA256: "+result["event_journal_sha256"],
        "",
        "## Historical coverage",
        "",
        "Event-time publication, provider first-seen, provider-available and processing-delivery timestamps are distinct. Only the independently attested first availability may determine an eligible NYSE open. News published after US market open cannot be used for that same earlier opening.",
        "GDELT 2.0 has reliable high-frequency archives from February 2015, not a timestamp-complete 2009–2026 feed. ALFRED keeps macro vintages, but release-day granularity alone does NOT prove pre-open knowledge. SEC filings require acceptance timestamp, verifiable dissemination and historical ticker mapping for company studies.",
        "",
        "## Research result",
        "",
        "No predictive alpha can be computed or validated without independently provenance-locked historical event snapshots, correct release expectations, and subsequent forward validation.",
        "An EMPTY journal deliberately produces a BLOCKED result: no fictional news events or invented backtest profits.",
        "",
        "## Real-data study rules",
        "",
        "Study actual QQQ/TQQQ OPEN to 1/5/21 SESSION CLOSE log returns for events with proven first-seen timestamps only. Do not conflate price reaction already occurred with return known at event time.",
        "Event observations overlap and are sourced from already-inspected historical periods. No iid inference, risk-budget recommendation, actual broker fills, or automatic 8.0 model promotion.",
        "",
    ]
    Path(report).parent.mkdir(parents=True,exist_ok=True)
    Path(report).write_text("\n".join(parts),encoding="utf-8")
    print("STOCKLENS_NEWS_PIT_RESULT="+json.dumps({
        "status":result["status"],"source_price_days":len(market["daily"]),
        "archived_news_records":result["news_source_records"],
        "point_in_time_eligible_events":result["actually_joined_eligible_market_events"],
        "capital_authorized":False,"model_mutated":False
    },sort_keys=True))
    return result


if __name__=="__main__":
    build()

"""News event as-of market joins. All mock news facts/prices are synthetic."""
from datetime import datetime
import hashlib

import exchange_calendars as xcals
import pytest

from news_event_pit import ingest_records, clean_event
from news_event_study import eligible_market_open, study


def event(event_id="NEWS-A",*,published="2024-03-20T18:00:00Z",
          first="2024-03-20T18:02:00Z",available="2024-03-20T18:04:00Z",
          evidence=True,kind="OUTCOME_RELEASED",category="FOMC_RATE"):
    return {
        "event_id":event_id,
        "canonical_story_id":"STORY-"+event_id,
        "provider":"SYNTHETIC_PIT_TEST",
        "source_record_id":"SOURCE-"+event_id,
        "category":category,"scope":"MARKET","event_kind":kind,
        "source_url":"https://example.invalid/"+event_id,
        "source_record_sha256":hashlib.sha256(event_id.encode()).hexdigest(),
        "published_at_utc":published,
        "provider_first_seen_at_utc":first,
        "provider_available_at_utc":available,
        "processing_delay_minutes":2,
        "archived_first_seen_verified":evidence,
        "first_seen_evidence_kind":"ARCHIVED_VENDOR_FIRST_SEEN",
        "first_seen_evidence_uri":"https://example.invalid/firstseen/"+event_id,
        "first_seen_archival_receipt_sha256":hashlib.sha256(("receipt-"+event_id).encode()).hexdigest()
    }


def rows():
    cal=xcals.get_calendar("XNYS")
    dates=cal.sessions_in_range("2024-03-18","2024-05-15")
    return [
        {"date":str(d.date()),"qo":100+i*.2,"qc":100.1+i*.2,
         "to":40+i*.5,"tc":40.15+i*.5,"l":3.0,
         "signal":(d.date().isoformat())}
        for i,d in enumerate(dates)
    ]


def test_fomc_release_after_open_cannot_trade_same_day_open():
    x=ingest_records([event()])["verified_distinct_events"][0]
    assert eligible_market_open(x)=="2024-03-21"
    output=study(rows(),ingest_records([event()]))
    assert output["status"]=="HISTORICAL_NEWS_EVENT_STUDY_DESCRIPTIVE_ONLY"
    e=output["event_cases"][0]
    assert e["first_tradable_open_session"]=="2024-03-21"
    assert e["shadow_only_action"]=="NO_CHANGE"
    assert e["frozen_target_unchanged"]==3.0
    assert e["market_reaction_not_prepublication_predictor"] is True
    assert set("observed_horizon_"+str(n) for n in (1,5,21)).issubset(e)
    assert output["capital_deployment_authorized"] is False
    assert output["event_based_model_prediction_proven"] is False


def test_bls_preopening_data_while_proven_available_can_map_same_day_open():
    x=event("CPI",published="2024-03-20T12:30:00Z",
        first="2024-03-20T12:32:00Z",
        available="2024-03-20T12:35:00Z",category="CPI")
    normalized=ingest_records([x])["verified_distinct_events"][0]
    assert eligible_market_open(normalized)=="2024-03-20"
    result=study(rows(),ingest_records([x]))
    assert result["event_cases"][0]["first_tradable_open_session"]=="2024-03-20"


def test_weekend_and_good_friday_never_create_fake_tradable_session():
    weekend=event("W",published="2024-03-23T10:00:00Z",
                  first="2024-03-23T10:10:00Z",
                  available="2024-03-23T10:11:00Z")
    holiday=event("H",published="2024-03-29T14:00:00Z",
                  first="2024-03-29T14:05:00Z",
                  available="2024-03-29T14:06:00Z")
    got=ingest_records([weekend,holiday])["verified_distinct_events"]
    assert [eligible_market_open(x) for x in got]==["2024-03-25","2024-04-01"]


def test_unverifiable_event_does_not_synthesize_backtested_alpha():
    output=study(rows(),ingest_records([event(evidence=False)]))
    assert output["status"]=="BLOCKED_NO_GENUINE_TIMESTAMPED_HISTORICAL_EVENT_COHORT"
    assert output["actually_joined_eligible_market_events"]==0
    assert output["blockers"]["no_pit_event_evidence"]==1
    assert output["event_cases"]==[]
    assert output["automatic_model_promotion"] is False


def test_calendar_schedule_cannot_be_future_actual_policy_signal():
    with pytest.raises(ValueError,match="NEWS_NO_VERIFIED_POINT_IN_TIME_FIRST_SEEN"):
        eventobj=clean_event(event(kind="SCHEDULE_ANNOUNCED"))
        eligible_market_open(eventobj)


def test_no_price_session_cannot_silently_use_next_available_price():
    a=rows()
    missing_date="2024-03-21"
    a=[x for x in a if x["date"]!=missing_date]
    s=study(a,ingest_records([event()]))
    assert s["actually_joined_eligible_market_events"]==0
    assert s["blockers"]["no_observed_next_open_session"]==1


def test_overlapping_stories_count_one_unique_event_once():
    b=event("NEWS-B",first="2024-03-20T18:06:00Z",
            available="2024-03-20T18:07:00Z")
    b["canonical_story_id"]="STORY-NEWS-A"
    x=ingest_records([event(),b])
    assert x["distinct_verified_stories"]==1
    out=study(rows(),x)
    assert out["actually_joined_eligible_market_events"]==1
    assert out["category_attribution"][0]["observed_event_count"]==1
    assert out["historical_samples_untouched_holdout"] is False


def test_news_after_last_observed_market_session_cannot_grade_its_future():
    x=event("LATE",published="2026-10-10T18:00:00Z",
            first="2026-10-10T18:02:00Z",
            available="2026-10-10T18:04:00Z")
    r=study(rows(),ingest_records([x]))
    assert r["actually_joined_eligible_market_events"]==0
    assert r["blockers"]["out_of_observed_cohort"]==1
    assert r["event_based_model_prediction_proven"] is False


def test_no_21day_future_does_not_turn_into_one_day_label():
    events=ingest_records([event("LAST",published="2024-05-14T18:00:00Z",
                     first="2024-05-14T18:02:00Z",
                     available="2024-05-14T18:04:00Z")])
    v=study(rows(),events)
    assert v["actually_joined_eligible_market_events"]==1
    assert "observed_horizon_21" not in v["event_cases"][0]
    assert v["blockers"]["missing_horizon_21"]==1


def test_compromised_ohlc_never_produces_fake_price_study():
    a=rows()
    a[10]["to"]=-1
    with pytest.raises(ValueError,match="NEWS_OBSERVED_ETF_PRICES_INVALID"):
        study(a,ingest_records([event()]))


def test_missing_middle_session_blocks_incorrect_horizon():
    a=[x for x in rows() if x["date"]!="2024-03-22"]
    e=study(a,ingest_records([event("GAP")]))["event_cases"][0]
    assert "observed_horizon_1" in e
    assert "observed_horizon_5" not in e
    assert "observed_horizon_21" not in e

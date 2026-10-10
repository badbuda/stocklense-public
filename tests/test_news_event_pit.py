"""Adversarial date/version/news lineage tests. All headlines are SYNTHETIC."""
from copy import deepcopy
import hashlib

import pytest

from news_event_pit import clean_event, ingest_records,load_journal
from news_provider_adapters import gdelt_2_gkg_row_to_event, sec_submission_rows,prepare_provider_rows


def event(oid="A", **kwargs):
    result={
        "event_id":oid, "canonical_story_id":"STORY-1",
        "provider":"ARCHIVE_TEST_ONLY",
        "source_record_id":oid,
        "category":"FOMC_RATE","scope":"MARKET",
        "event_kind":"OUTCOME_RELEASED",
        "source_url":"https://example.invalid/archive/"+oid,
        "source_record_sha256":hashlib.sha256(oid.encode()).hexdigest(),
        "published_at_utc":"2024-03-20T18:00:00Z",
        "provider_first_seen_at_utc":"2024-03-20T18:02:00Z",
        "provider_available_at_utc":"2024-03-20T18:04:00Z",
        "processing_delay_minutes":2,
        "archived_first_seen_verified":True,
        "first_seen_evidence_kind":"ARCHIVED_VENDOR_FIRST_SEEN",
        "first_seen_evidence_uri":"https://example.invalid/immutable/"+oid,
    }
    result.update(kwargs)
    return result


def test_verified_archive_attests_time_not_prediction_of_outcome():
    x=clean_event(event())
    assert x["first_seen_proven"] is True
    assert x["signal_ready_at_utc"]=="2024-03-20T18:16:00+00:00"
    assert x["automated_live_trade_eligible"] is False
    assert x["sentiment_from_modern_LLM_used_for_historical_trading"] is False
    assert x["event_surprise_if_consensus_verified"] is None


def test_schedule_does_not_foresee_fomc_outcome():
    x=clean_event(event(event_kind="SCHEDULE_ANNOUNCED"))
    assert x["first_seen_proven"] is False
    with pytest.raises(ValueError,match="NEWS_PARTIAL_OR_PREANNOUNCED_SURPRISE"):
        clean_event(event(event_kind="SCHEDULE_ANNOUNCED",actual_value=.25,expected_value=.5))


def test_true_surprise_only_with_archived_pre_release_consensus():
    a=event(actual_value=.25,expected_value=.5,
            expectation_snapshot_at_utc="2024-03-20T17:00:00Z",
            consensus_pit_verified=True,
            expectation_source_uri="https://example.invalid/consensus/before")
    x=clean_event(a)
    assert x["event_surprise_if_consensus_verified"]==pytest.approx(-.25)
    assert x["first_seen_proven"] is True
    a["expectation_snapshot_at_utc"]="2024-03-20T18:00:00Z"
    with pytest.raises(ValueError,match="NEWS_EXPECTATION_COLLECTED_AFTER_PUBLICATION"):
        clean_event(a)
    a["expectation_snapshot_at_utc"]="2024-03-20T17:00:00Z"
    a["consensus_pit_verified"]=False
    assert clean_event(a)["first_seen_proven"] is False


def test_first_seen_unverified_and_llm_rewritten_past_news_blocked():
    assert clean_event(event(archived_first_seen_verified=False))["first_seen_proven"] is False
    assert clean_event(event(analysis_generated_at_utc="2026-10-10T11:00:00Z"))["first_seen_proven"] is False
    x=event(scope="COMPANY",category="M_AND_A",affected_tickers=["NVDA"])
    assert clean_event(x)["first_seen_proven"] is False
    x["ticker_mapping_point_in_time_verified"]=True
    assert clean_event(x)["first_seen_proven"] is True


@pytest.mark.parametrize("patch,code",[
    ({"provider_first_seen_at_utc":"2024-03-20T17:00:00Z"},"NEWS_IMPOSSIBLE_PUBLICATION_AVAILABILITY_ORDER"),
    ({"published_at_utc":"2024-03-20"},"NEWS_MISSING_PRECISE_TIMESTAMP"),
    ({"provider_available_at_utc":"2024-03-20T18:00:00Z"},"NEWS_IMPOSSIBLE_PUBLICATION_AVAILABILITY_ORDER"),
    ({"source_url":"http://example.org/plain"},"NEWS_NONHTTPS_OR_CREDENTIAL_URL"),
    ({"source_record_sha256":"abc"},"NEWS_SOURCE_SHA256_REQUIRED"),
    ({"category":"POSTHOC_WINNER_2024"},"NEWS_CATEGORY_OR_SCOPE_UNREGISTERED"),
    ({"processing_delay_minutes":-1},"NEWS_PROCESSING_DELAY_NOT_DEFINED"),
    ({"processing_delay_minutes":float("nan")},"NEWS_PROCESSING_DELAY_NOT_DEFINED"),
    ({"archived_first_seen_verified":None},"NEWS_FIRST_SEEN_BOOLEAN_MISSING"),
])
def test_fails_closed_on_bogus_news_metadata(patch,code):
    with pytest.raises(ValueError,match=code):
        clean_event(event(**patch))


def test_syndicated_story_dedup_prefers_earliest_eligible_verified_source():
    unverified=event("A",archived_first_seen_verified=False)
    different_provider=event("B",provider_available_at_utc="2024-03-20T18:20:00Z",
                             first_seen_evidence_uri="https://example.invalid/immutable/B")
    latest=event("C",canonical_story_id="STORY-2",
                 provider_available_at_utc="2024-03-20T19:20:00Z")
    records=ingest_records([latest,different_provider,unverified])
    assert records["raw_event_records"]==3
    assert records["source_verified_records"]==2
    assert records["distinct_verified_stories"]==2
    assert [x["event_id"] for x in records["verified_distinct_events"]]==["B","C"]
    with pytest.raises(ValueError,match="NEWS_DUPLICATE_EVENT_RECORD_ID"):
        ingest_records([event("A"),event("A")])


def test_empty_journal_explicitly_not_tested_news_strategy(tmp_path):
    audit=load_journal(tmp_path/"no-news.jsonl")
    assert audit["status"]=="DATA_BLOCKED_NO_PIT_VERIFIED_EVENTS"
    assert audit["distinct_verified_stories"]==0
    assert audit["automatic_strategy_change"] is False
    assert audit["capital_deployment_authorized"] is False


def test_real_gdelt_gkg_schema_ingests_only_unverified_metadata():
    fields=[""]*27
    fields[0]="20150301120000-987"
    fields[1]="20150301120000"
    fields[3]="Example outlet"
    fields[4]="https://example.org/world/story"
    fields[7]="ARMEDCONFLICT;KILL"
    raw=gdelt_2_gkg_row_to_event("\t".join(fields))
    assert raw["category"]=="WAR_CONFLICT"
    assert raw["provider"]=="GDELT_2_0_GKG"
    assert prepare_provider_rows([raw])[0]["first_seen_proven"] is False
    fields[7]="ECON_UNKNOWN"
    raw=gdelt_2_gkg_row_to_event("\t".join(fields))
    assert raw["category"]=="UNCLASSIFIED_NEWS"
    with pytest.raises(ValueError,match="GDELT_GKG_TIMESTAMP_INVALID"):
        fields[1]="2015-03-01"
        gdelt_2_gkg_row_to_event("\t".join(fields))


def test_sec_acceptance_never_proves_actual_article_time_or_what_8k_contains():
    raw={"filings":{"recent":{
        "form":["8-K","10-Q","SC 13G"],
        "accessionNumber":["0001234567-24-000042","0001234567-24-000043","0001234567-24-000044"],
        "primaryDocument":["a.htm","b.htm","c.htm"],
        "acceptanceDateTime":["2024-03-20T18:01:00Z","2024-03-21T13:00:00Z","2024-03-21T13:00:00Z"]}}}
    out=sec_submission_rows(raw,cik="0001234567",ticker_mapping=["NVDA"])
    assert len(out)==2
    assert all(x["category"]=="CORPORATE_FILING" for x in out)
    assert all(x["archived_first_seen_verified"] is False for x in out)
    assert all(x["ticker_mapping_point_in_time_verified"] is False for x in out)
    assert all(clean_event(x)["first_seen_proven"] is False for x in out)
    raw["filings"]["recent"]["acceptanceDateTime"][0]="2024-03-20T14:01:00"
    assert len(sec_submission_rows(raw,cik="0001234567",ticker_mapping=["NVDA"]))==1


def test_repeated_event_jsonl_is_an_error_not_silent_retrospective_revision(tmp_path):
    import json
    p=tmp_path/"events.jsonl"
    p.write_text(json.dumps(event())+"\n"+json.dumps(event())+"\n",encoding="utf-8")
    with pytest.raises(ValueError,match="NEWS_DUPLICATE_EVENT_RECORD_ID"):
        load_journal(p)

"""StockLens: point-in-time news EVENT EVIDENCE, not a trading oracle.

Classifies *provided* event metadata and verifies the signal-availability
contract before any historical ETF event study. It NEVER fetches, writes into,
or overrides the frozen 8.0 signal. No article body is stored. Missing
independent historical first-seen evidence always fails closed.

The three distinct clocks matter:
  event occurrence    != press publication != vendor first seen/availability.
A scheduled FOMC/CPI calendar entry NEVER discloses the decision/result.
A modern LLM analyzing 2015 news may know its future outcomes: model-authored
past sentiment is NOT contemporaneously tradable without extra validation.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path
import re
from urllib.parse import urlsplit

CATEGORIES = (
    "FOMC_RATE", "CPI", "JOBS", "GDP", "CENTRAL_BANK_SPEECH",
    "WAR_CONFLICT", "ELECTION_RESULT", "SANCTIONS_TARIFFS",
    "CORPORATE_FILING", "EARNINGS_GUIDANCE", "M_AND_A",
    "REGULATION", "CYBER_INCIDENT", "CREDIT_EVENT", "UNCLASSIFIED_NEWS",
)
SCOPES = ("MARKET", "COMPANY", "SECTOR")
ALLOWED_EVENT_KINDS = ("OUTCOME_RELEASED", "SCHEDULE_ANNOUNCED")
PIT_FIRST_SEEN_KINDS = (
    "ARCHIVED_VENDOR_FIRST_SEEN", "IMMUTABLE_LIVE_COLLECTOR_RECEIPT",
)
DEFAULT_JOURNAL = Path("research/private/news_pit_verified.jsonl")
PROTECTION_MINUTES = 10
SHA_PATTERN = re.compile(r"^[0-9a-f]{64}$")


def utc(value, name):
    if not isinstance(value, str) or len(value) < 20:
        raise ValueError("NEWS_MISSING_PRECISE_TIMESTAMP:"+name)
    try:
        dt = datetime.fromisoformat(value.replace("Z","+00:00"))
    except (ValueError, OverflowError) as exc:
        raise ValueError("NEWS_INVALID_TIMESTAMP:"+name) from exc
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("NEWS_NAIVE_TIME_FORBIDDEN:"+name)
    return dt.astimezone(timezone.utc)


def _nonempty(value, name):
    if not isinstance(value,str) or not value.strip() or len(value)>1024:
        raise ValueError("NEWS_REQUIRED_SOURCE_FIELD:"+name)
    return value.strip()


def clean_event(x):
    """Normalize and reject impossible clocks; evidence-grade events only."""
    if not isinstance(x,dict):
        raise ValueError("NEWS_EVENT_NOT_OBJECT")
    id_ = _nonempty(x.get("event_id"),"event_id")
    story = _nonempty(x.get("canonical_story_id"),"canonical_story_id")
    provider = _nonempty(x.get("provider"),"provider")
    source_id = _nonempty(x.get("source_record_id"),"source_record_id")
    category=x.get("category")
    scope=x.get("scope")
    kind=x.get("event_kind")
    if category not in CATEGORIES or scope not in SCOPES:
        raise ValueError("NEWS_CATEGORY_OR_SCOPE_UNREGISTERED")
    if kind not in ALLOWED_EVENT_KINDS:
        raise ValueError("NEWS_EVENT_KIND_UNREGISTERED")
    url=_nonempty(x.get("source_url"),"source_url")
    parsed=urlsplit(url)
    if parsed.scheme!="https" or not parsed.netloc or parsed.username or parsed.password:
        raise ValueError("NEWS_NONHTTPS_OR_CREDENTIAL_URL")
    digest=x.get("source_record_sha256")
    if not isinstance(digest,str) or not SHA_PATTERN.fullmatch(digest):
        raise ValueError("NEWS_SOURCE_SHA256_REQUIRED")
    publish=utc(x.get("published_at_utc"),"published_at_utc")
    firstseen=utc(x.get("provider_first_seen_at_utc"),"provider_first_seen_at_utc")
    available=utc(x.get("provider_available_at_utc"),"provider_available_at_utc")
    if not publish<=firstseen<=available:
        raise ValueError("NEWS_IMPOSSIBLE_PUBLICATION_AVAILABILITY_ORDER")
    lag=x.get("processing_delay_minutes")
    if type(lag) not in (int,float) or not math.isfinite(lag) or lag<0 or lag>1440:
        raise ValueError("NEWS_PROCESSING_DELAY_NOT_DEFINED")
    firstseen_kind=x.get("first_seen_evidence_kind")
    witnessed=bool(x.get("archived_first_seen_verified") is True)
    receipt_sha=x.get("first_seen_archival_receipt_sha256")
    receipt_uri=x.get("first_seen_evidence_uri")
    proof_url=urlsplit(receipt_uri) if isinstance(receipt_uri,str) else None
    proof_acceptable=(proof_url is not None and proof_url.scheme=="https"
                      and bool(proof_url.netloc) and not proof_url.username
                      and not proof_url.password)
    verified=(witnessed and firstseen_kind in PIT_FIRST_SEEN_KINDS
              and proof_acceptable and isinstance(receipt_sha,str)
              and bool(SHA_PATTERN.fullmatch(receipt_sha)))
    if x.get("archived_first_seen_verified") not in (True,False):
        raise ValueError("NEWS_FIRST_SEEN_BOOLEAN_MISSING")
    if firstseen_kind is not None and (
        not isinstance(firstseen_kind,str) or len(firstseen_kind)>100
    ):
        raise ValueError("NEWS_INVALID_FIRST_SEEN_PROOF_KIND")
    # Only a future-live model output can be as-of a new session. A fresh LLM
    # rewrite of 2015 articles MUST NOT be treated as a 2015 ML forecast.
    model_at=x.get("analysis_generated_at_utc")
    if model_at is not None:
        created=utc(model_at,"analysis_generated_at_utc")
        if created>available:
            verified=False
    if scope=="COMPANY" and x.get("ticker_mapping_point_in_time_verified") is not True:
        verified=False
    tickers=x.get("affected_tickers",[])
    if not isinstance(tickers,list) or not all(
        isinstance(t,str) and 1<=len(t)<=12 and t.isascii() and t.isupper()
        for t in tickers
    ):
        raise ValueError("NEWS_TICKERS_MUST_BE_POINT_IN_TIME_SYMBOLS")
    if scope=="COMPANY" and not tickers:
        verified=False
    if kind=="SCHEDULE_ANNOUNCED":
        # Even a proven event-calendar release cannot transmit the future
        # actual decision. It can ONLY be used for calendar/risk scheduling.
        verified=False
    surprise=None
    if x.get("actual_value") is not None or x.get("expected_value") is not None:
        if kind!="OUTCOME_RELEASED" or x.get("actual_value") is None or x.get("expected_value") is None:
            raise ValueError("NEWS_PARTIAL_OR_PREANNOUNCED_SURPRISE")
        actual,expected=x["actual_value"],x["expected_value"]
        if type(actual) not in (int,float) or type(expected) not in (int,float):
            raise ValueError("NEWS_EXPECTED_AND_ACTUAL_MUST_BE_FINITE_NUMBERS")
        if not(math.isfinite(actual) and math.isfinite(expected)):
            raise ValueError("NEWS_EXPECTED_AND_ACTUAL_NONFINITE")
        expectation_time=utc(x.get("expectation_snapshot_at_utc"),"expectation_snapshot_at_utc")
        if expectation_time>=publish:
            raise ValueError("NEWS_EXPECTATION_COLLECTED_AFTER_PUBLICATION")
        if x.get("consensus_pit_verified") is not True or not x.get("expectation_source_uri"):
            verified=False
        else:
            surprise=actual-expected
    available_trade=available+timedelta(minutes=float(lag)+PROTECTION_MINUTES)
    canonical={
        "event_id":id_, "canonical_story_id":story, "provider":provider,
        "source_record_id":source_id, "category":category, "scope":scope,
        "event_kind":kind, "source_url":url, "source_record_sha256":digest,
        "published_at_utc":publish.isoformat(),
        "provider_first_seen_at_utc":firstseen.isoformat(),
        "provider_available_at_utc":available.isoformat(),
        "signal_ready_at_utc":available_trade.isoformat(),
        "first_seen_evidence_kind":firstseen_kind,
        "first_seen_archival_receipt_sha256":receipt_sha if proof_acceptable else None,
        "first_seen_proven":verified,
        "event_surprise_if_consensus_verified":surprise,
        "affected_tickers":sorted(set(tickers)),
        "company_ticker_mapping_point_in_time_verified":(
            x.get("ticker_mapping_point_in_time_verified") is True),
        "classification_method":"SOURCE_EVENT_TAXONOMY_ONLY",
        "sentiment_from_modern_LLM_used_for_historical_trading":False,
        "raw_article_text_stored":False,
        "automated_live_trade_eligible":False,
    }
    return canonical


def ingest_records(records):
    """Immutable story dedupe: do not count the same syndicated event 30x."""
    if not isinstance(records,list):
        raise ValueError("NEWS_EVENTS_NOT_LIST")
    clean=[clean_event(e) for e in records]
    identities=[e["event_id"] for e in clean]
    if len(identities)!=len(set(identities)):
        raise ValueError("NEWS_DUPLICATE_EVENT_RECORD_ID")
    # Preserve every original normalized record for provenance; choose only
    # first verified, independently time-attested source of each story for
    # the predictor, rather than choosing the later high-impact headline.
    observed={}
    for x in sorted(clean,key=lambda r:(r["signal_ready_at_utc"],r["event_id"])):
        key=x["canonical_story_id"]
        if x["first_seen_proven"] and key not in observed:
            observed[key]=x
    eligible=sorted(observed.values(),key=lambda x:(x["signal_ready_at_utc"],x["event_id"]))
    journal_fingerprint=hashlib.sha256(json.dumps(clean,sort_keys=True,
                          separators=(",",":")).encode()).hexdigest()
    return {
        "status":"HAS_PIT_ELIGIBLE_EVENTS" if eligible else "DATA_BLOCKED_NO_PIT_VERIFIED_EVENTS",
        "raw_event_records":len(clean),
        "source_verified_records":sum(x["first_seen_proven"] for x in clean),
        "distinct_verified_stories":len(eligible),
        "rejected_or_duplicate_records":len(clean)-len(eligible),
        "normalized_event_journal_sha256":journal_fingerprint,
        "verified_distinct_events":eligible,
        "all_original_event_metadata_proven":False,
        "independent_historical_source_first_seen_required":True,
        "automatic_strategy_change":False,
        "capital_deployment_authorized":False,
    }


def load_journal(path=DEFAULT_JOURNAL):
    p=Path(path)
    if not p.exists():
        return ingest_records([])
    if p.stat().st_size>64*1024*1024:
        raise ValueError("NEWS_EVENT_ARCHIVE_TOO_LARGE_FOR_SINGLE_PASS")
    rows=[]
    for number,line in enumerate(p.read_text(encoding="utf-8").splitlines(),1):
        if line.strip():
            try:record=json.loads(line)
            except ValueError as exc:raise ValueError(
                "NEWS_INVALID_JSONL_LINE:"+str(number)) from exc
            # Untrusted disk JSONL cannot independently attest historical
            # vendor first-seen. An HTTPS URL and hash are not a receipt check.
            if isinstance(record,dict):
                record={**record,"archived_first_seen_verified":False}
            rows.append(record)
    return ingest_records(rows)

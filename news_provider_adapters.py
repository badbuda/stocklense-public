"""Provider adapters: official market news metadata, NO claimed historical alpha.

Do not turn an SEC 8-K into a claimed acquisition without reading dated filing
items. Do not treat a GDELT record's 'event occurred' date as FIRST AVAILABLE.
Adapters produce unverified observations until a genuine historical first-seen
archive/immutable live collector receipt is attached as independent proof.
No article body/text is copied into public GitHub.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import io
import json
import re
from urllib.parse import quote

from news_event_pit import clean_event

SEC_CATEGORIES={"8-K","10-Q","10-K","6-K","20-F","40-F"}
SEC_SUBMISSION_PREFIX="https://www.sec.gov/Archives/edgar/data/"
GDELT_UTC_RE=re.compile(r"^\d{14}$")


def _source_sha(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False,
                            separators=(",",":")).encode("utf-8")).hexdigest()


def gdelt_2_gkg_row_to_event(row, *, archival_batch_available_at_utc=None):
    """GDELT 2.0 GKG v2.1 TSV fields, not the GDELT Event/Mentions table.

    Columns: 0 record ID, 1 DATE (14 digit GKG record UTC), 3 SourceCommonName,
    4 DocumentIdentifier, 7 Themes. GKG classification is NOT a verified
    publication clock or a tradable story/war declaration.
    """
    fields=row.split("\t") if isinstance(row,str) else list(row)
    if len(fields)<16:
        raise ValueError("GDELT_GKG_FIELDS_TRUNCATED")
    record_id=fields[0]
    dt14=fields[1]
    if not GDELT_UTC_RE.fullmatch(dt14):
        raise ValueError("GDELT_GKG_TIMESTAMP_INVALID")
    src_date=datetime.strptime(dt14,"%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    url=fields[4]
    if not isinstance(url,str) or not url.startswith(("https://","http://")):
        raise ValueError("GDELT_GKG_SOURCE_ARTICLE_MISSING")
    # Multiple article URLs are often discovered in a single GKG batch.
    # We may index the source URL, but NO first-seen publication proof exists
    # merely because the GKG DATE column contains a 14-digit time.
    if not url.startswith("https://"):
        raise ValueError("GDELT_NEWS_ARTICLE_MUST_USE_HTTPS")
    batch=(datetime.fromisoformat(archival_batch_available_at_utc.replace("Z","+00:00"))
           if archival_batch_available_at_utc is not None else src_date+timedelta(minutes=15))
    if batch.tzinfo is None:
        raise ValueError("GDELT_ARCHIVE_BATCH_TIMEZONE_REQUIRED")
    if batch < src_date:
        raise ValueError("GDELT_BATCH_CANNOT_PREDATE_RECORD")
    raw={
        "event_id":"GDELT-GKG-"+record_id,
        "canonical_story_id":"GDELT-URL-"+hashlib.sha256(url.encode()).hexdigest(),
        "provider":"GDELT_2_0_GKG",
        "source_record_id":record_id,
        "category":"WAR_CONFLICT" if any(
            t in fields[7].split(";") for t in (
                "ARMEDCONFLICT","MILITARY","KILL","TERROR")
        ) else "REGULATION",
        "scope":"MARKET",
        "event_kind":"OUTCOME_RELEASED",
        "source_url":url,
        "source_record_sha256":_source_sha({"gkg_record_id":record_id,
             "batch_date_utc":dt14,"source_document_url":url,"themes":fields[7]}),
        "published_at_utc":src_date.isoformat(),
        "provider_first_seen_at_utc":src_date.isoformat(),
        "provider_available_at_utc":batch.astimezone(timezone.utc).isoformat(),
        "processing_delay_minutes":15,
        "archived_first_seen_verified":False,
        "first_seen_evidence_kind":"GDELT_GKG_BATCH_NOT_INDEPENDENT_FIRST_SEEN",
        "first_seen_evidence_uri":"",
    }
    # Classification is a loose research taxonomy ONLY, not evidence of a
    # new war, political surprise, or causal market impact.
    return raw


def sec_submission_rows(submissions_json, *, cik, ticker_mapping=None):
    """Read public SEC submissions.recent arrays without a network call.

    SEC filing acceptance time is NOT necessarily first executable access.
    A 10-K/8-K filing does not itself establish positive or negative guidance,
    M&A consummation or security P&L impact; text must be checked separately.
    """
    data=submissions_json
    if not isinstance(data,dict):
        raise ValueError("SEC_SUBMISSIONS_NOT_OBJECT")
    recent=data.get("filings",{}).get("recent",{})
    required=("form","accessionNumber","primaryDocument","acceptanceDateTime")
    if not isinstance(recent,dict) or not all(isinstance(recent.get(x),list) for x in required):
        raise ValueError("SEC_MISSING_SUBMISSIONS_RECENT_COLUMNS")
    lengths={len(recent[x]) for x in required}
    if len(lengths)!=1:
        raise ValueError("SEC_SUBMISSION_ARRAYS_DIFFERENT_LENGTHS")
    out=[]
    for j,form in enumerate(recent["form"]):
        if form not in SEC_CATEGORIES:continue
        accession=recent["accessionNumber"][j]
        doc=recent["primaryDocument"][j]
        at=recent["acceptanceDateTime"][j]
        if not (isinstance(at,str) and ("Z" in at or "+" in at or
                at.endswith("00:00"))):
            # SEC JSON can give a naive timestamp; never assume UTC/ET
            # without a versioned native source contract for this field.
            continue
        try:published=datetime.fromisoformat(at.replace("Z","+00:00"))
        except ValueError:continue
        if published.tzinfo is None:continue
        if not re.fullmatch(r"\d{10}",str(cik)) or not re.fullmatch(
                r"\d{10}-\d{2}-\d{6}",str(accession)):
            raise ValueError("SEC_INVALID_CIK_OR_ACCESSION")
        if not isinstance(doc,str) or "/" in doc or ".." in doc:
            raise ValueError("SEC_INVALID_PRIMARY_DOCUMENT")
        url=(SEC_SUBMISSION_PREFIX+str(int(cik))+"/"+
             accession.replace("-","")+"/"+quote(doc))
        raw={
            "event_id":"SEC-"+accession,
            "canonical_story_id":"SEC-FILING-"+accession,
            "provider":"SEC_EDGAR_SUBMISSIONS",
            "source_record_id":accession,
            "source_url":url,
            "source_record_sha256":_source_sha({"cik":cik,"acceptance":at,
                    "form":form,"accession":accession,"primary":doc}),
            "category":"CORPORATE_FILING","scope":"COMPANY",
            "event_kind":"OUTCOME_RELEASED",
            "published_at_utc":published.astimezone(timezone.utc).isoformat(),
            "provider_first_seen_at_utc":published.astimezone(timezone.utc).isoformat(),
            "provider_available_at_utc":published.astimezone(timezone.utc).isoformat(),
            "processing_delay_minutes":5,
            "archived_first_seen_verified":False,
            "first_seen_evidence_kind":"SEC_ACCEPTANCE_NOT_INDEPENDENT_DELIVERY",
            "first_seen_evidence_uri":"",
            "affected_tickers":list(ticker_mapping or []),
            "ticker_mapping_point_in_time_verified":False,
        }
        out.append(raw)
    return out


def prepare_provider_rows(events):
    """Output only strict normalized, unverified initial intake metadata."""
    return [clean_event(x) for x in events]

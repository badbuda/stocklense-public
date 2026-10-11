"""Bounded read-only GitHub server arrival and expiring artifact audit.

Running on GitHub Actions obtains GitHub-server event timestamps; it NEVER
proves contemporaneous MARKET DATA collection, Git actor clock, live fills,
nor SL9-007 independent forward capture. No automation orders or token logs.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import json
import os
import zipfile
import io
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT="https://api.github.com/repos/badbuda/stocklense-public"
OUT=Path("research/results/sl9_022_github_server_receipts.json")
ARCHIVE=Path("research/private/sl9_022_archived_prior_ci")
ARTIFACT_IDS=(11530228655,11562024976,11595483058,11656109189)
TARGET_COMMITS=("d54464f854c90eeddd7a008c65c1314dff2ac41e",
                "336d67ea540126d0ec64834d5e8d79e94d0683b0",
                "637ee8d731a2759b5401699d86f2b66e33a9f667")
MAX_EVENTS_PAGES=3
MAX_ZIP=9_000_000


def get(rel,limit=MAX_ZIP):
    if not isinstance(rel,str) or not rel.startswith("/") or "//" in rel or ".." in rel:
        raise ValueError("GITHUB_UNSAFE_RELATIVE_ENDPOINT")
    headers={"Accept":"application/vnd.github+json",
       "User-Agent":"StockLens-readonly-artifact-preservation/1.0",
       "X-GitHub-Api-Version":"2022-11-28"}
    token=os.getenv("GITHUB_TOKEN","")
    if token:headers["Authorization"]="Bearer "+token
    request=Request(ROOT+rel,headers=headers)
    with urlopen(request,timeout=35) as resp:
        raw=resp.read(limit+1)
    if len(raw)>limit:raise ValueError("GITHUB_RESPONSE_LIMIT_EXCEEDED")
    return raw


def report_event_pages(page_bytes):
    seen={}
    receipts=[]
    page_digests=[]
    for page_index,raw in enumerate(page_bytes,1):
        page_digests.append({"page":page_index,"sha256":hashlib.sha256(raw).hexdigest(),
                             "raw_bytes":len(raw)})
        items=json.loads(raw)
        if not isinstance(items,list):raise ValueError("EVENTS_API_UNEXPECTED_RESPONSE")
        for event in items:
            if not isinstance(event,dict):raise ValueError("EVENTS_API_BAD_ROW")
            typ=event.get("type")
            if typ!="PushEvent":continue
            payload=event.get("payload") or {}
            identifiers=[payload.get("head")]
            identifiers += [e.get("sha") for e in payload.get("commits",[])
                            if isinstance(e,dict)]
            identifiers=[x for x in identifiers if isinstance(x,str)]
            row={"event_id":str(event.get("id")),
                 "github_server_created_at":event.get("created_at"),
                 "event_type":typ,"pushed_ref":payload.get("ref"),
                 "head_commit":payload.get("head"),
                 "event_page":page_index,
                 "client_git_author_date_used_as_receipt":False,
                 "provider_market_data_first_seen_proven":False}
            receipts.append(row)
            for cid in TARGET_COMMITS:
                if cid in identifiers:
                    seen[cid]=row
    return {"schema_version":1,
            "kind":"GITHUB_PUBLIC_EVENT_SERVER_RECEIPT_SEARCH",
            "source":ROOT+"/events (bounded latest 300 public events)",
            "pages_hashed":page_digests,
            "push_events_summarized":len(receipts),
            "target_sha_matched_server_events":seen,
            "target_sha_not_found":[s for s in TARGET_COMMITS if s not in seen],
            "server_event_receipt_alone_proves_market_capture":False,
            "git_author_time_independent_receipt":False,
            "zero_fills_or_market_timestamps_inferred":True}


def inspect_zip(raw,artifact_id):
    if len(raw)>MAX_ZIP:raise ValueError("PRIOR_ARTIFACT_TOO_LARGE")
    z=zipfile.ZipFile(io.BytesIO(raw))
    names=z.namelist()
    if len(names)>500:raise ValueError("PRIOR_ARTIFACT_TOO_MANY_ENTRIES")
    if any(n.startswith("/") or ".." in Path(n).parts for n in names):
        raise ValueError("UNSAFE_ORIGINAL_ARTIFACT_ZIP")
    return {"id":artifact_id,"zip_sha256":hashlib.sha256(raw).hexdigest(),
            "bytes":len(raw),"entries":len(names),
            "zip_integrity":"READABLE_CENTRAL_DIRECTORY",
            "original_market_first_seen_proven":False}


def build():
    OUT.parent.mkdir(parents=True,exist_ok=True)
    ARCHIVE.mkdir(parents=True,exist_ok=True)
    result={"schema_version":1,"kind":"SL9_022_TIME_LIMITED_GITHUB_RESEARCH_RECEIPTS",
        "read_only_source":"GITHUB_REST_API_SERVER",
        "collected_at_runner_utc":datetime.now(timezone.utc).isoformat(),
        "gh_push_server_dates_not_vendor_market_receipts":True,
        "artifact_bytes_backfilled_as_trading_rows":False,
        "live_broker_trading_authorized":False,
        "source_errors":[],
        "saved_original_artifact_zip_snapshots":[]}
    pages=[]
    for page in range(1,MAX_EVENTS_PAGES+1):
        try:
            raw=get(f"/events?per_page=100&page={page}",limit=3_000_000)
            pages.append(raw)
            if len(json.loads(raw))<100:break
        except (HTTPError,URLError,OSError,ValueError,TimeoutError,json.JSONDecodeError) as exc:
            result["source_errors"].append({"endpoint":"public_events",
                                            "page":page,"reason":str(exc)[:180]})
            break
    if pages:
        result["events"]=report_event_pages(pages)
    else:
        result["events"]={"status":"BLOCKED_NO_READABLE_GITHUB_EVENTS",
                          "market_first_seen_proven":False}
    for artifact_id in ARTIFACT_IDS:
        try:
            info=json.loads(get(f"/actions/artifacts/{artifact_id}",limit=200_000))
            if info.get("expired") or info.get("id")!=artifact_id:
                raise ValueError("PRIOR_ARTIFACT_EXPIRED_OR_ID_MISMATCH")
            base={"id":artifact_id,"name":info.get("name"),
                  "created_at":info.get("created_at"),
                  "expires_at":info.get("expires_at"),
                  "github_artifact_size_in_bytes":info.get("size_in_bytes"),
                  "gh_server_created_time_only":True}
            try:
                raw=get(f"/actions/artifacts/{artifact_id}/zip",limit=MAX_ZIP)
                metadata=inspect_zip(raw,artifact_id)
                dest=ARCHIVE / f"artifact_{artifact_id}.zip"
                dest.write_bytes(raw)
                base.update(metadata)
                base["copy_status"]="PRESERVED_IN_THIS_RUN_ARCHIVE_ONLY"
            except (HTTPError,URLError,OSError,ValueError,TimeoutError,
                    zipfile.BadZipFile) as exc:
                base["copy_status"]="BLOCKED_DOWNLOAD"
                base["copy_error"]=str(exc)[:180]
            result["saved_original_artifact_zip_snapshots"].append(base)
        except (HTTPError,URLError,OSError,ValueError,TimeoutError,json.JSONDecodeError) as exc:
            result["saved_original_artifact_zip_snapshots"].append({
                "id":artifact_id,"copy_status":"BLOCKED_ARTIFACT_METADATA",
                "reason":str(exc)[:180]})
    result["provider_market_first_seen_verified"]=False
    result["original_sl9_007_paper_rows_qualified"]=0
    OUT.write_text(json.dumps(result,sort_keys=True,indent=2)+"\n")
    print("STOCKLENS_GITHUB_SERVER_RECEIPTS="+json.dumps({
        "events_status":(result["events"].get("status","FETCHED_LATEST_EVENTS")),
        "event_pages":len(pages),
        "matched_git_target_commits":len(result["events"].get("target_sha_matched_server_events",{})),
        "original_artifact_zip_copies":sum(x.get("copy_status")=="PRESERVED_IN_THIS_RUN_ARCHIVE_ONLY"
                                           for x in result["saved_original_artifact_zip_snapshots"]),
        "original_artifact_ids":list(ARTIFACT_IDS),
        "market_first_seen_verified":False},sort_keys=True))
    return result


if __name__=="__main__":
    build()

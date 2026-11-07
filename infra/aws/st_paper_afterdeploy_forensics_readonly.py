#!/usr/bin/env python3
"""StockLens ST after-deploy evidence triage (STRICT READ ONLY).

This tool does not invoke Lambda, replay Paper, repair continuity, clear alarms,
write S3, touch a broker, mutate EventBridge/CFN or conceal missing sessions.

It distinguishes: (1) verified code release, (2) S3 object existence with
version IDs (NOT proof of accounted Paper), (3) CloudWatch alarm states and
(4) watchdog/Lambda log evidence. Paper paths are hints, never an assumed
canonical ledger schema; only the independent readiness/ledger validator can
later establish a qualified chain.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone, timedelta
import json
import re
import sys

from infra.aws import st_paper_weekend_direct_guarded_release as release

BUCKET = release.p.ST_BUCKET
ST = release.ST
S3_KEYS = lambda day: {
    "signal": f"signals/{day}.json",
    "paper_session_guess": f"paper/sessions/{day}.json",
    "continuity_guess": f"paper/continuity/{day}.json",
}
ST_ALARM_PREFIX = "stocklens-st"
WATCHDOG_GROUP = "/aws/lambda/stocklens-st-session-watchdog"
PAPER_GROUP = "/aws/lambda/stocklens-st-paper-candidate"
ISSUES = (
    "SESSION_WITHOUT_CONTINUITY_RECORD",
    "TOO_FEW_MINUTE_BARS",
    "INTRADAY_FETCH_FAILED",
    "MISSED_SHADOW_SESSION",
    "PaperIntegrityError",
    "FAIL_CLOSED",
    "NOT_COMPLETED_US_MARKET_SESSION",
)
LIMIT_LOG = 100
MAX_LOG_PAGES = 3
MAX_S3_PAGES = 8


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def s3_head(s3, key):
    try:
        meta = s3.head_object(Bucket=BUCKET, Key=key)
    except Exception as exc:
        error = (getattr(exc, "response", {}) or {}).get("Error", {})
        code = str(error.get("Code", ""))
        if code in ("404", "NoSuchKey", "NotFound"):
            return {"status":"NOT_FOUND_AT_PROBED_KEY"}
        if code in ("403", "AccessDenied"):
            return {"status":"ACCESS_DENIED_UNVERIFIED"}
        return {"status":"READ_ERROR", "error_code": code or type(exc).__name__}
    version = meta.get("VersionId")
    if not version or version == "null":
        return {"status":"PRESENT_BUT_NO_VERSION_ID_UNVERIFIED"}
    return {
        "status":"VERSIONED_PRESENT_NOT_PAPER_ATTESTATION",
        "version_id_present": True,
        "size_bytes": meta.get("ContentLength", 0),
    }


def paper_version_inventory(s3, sessions):
    args = {"Bucket": BUCKET, "Prefix":"paper/", "MaxKeys":1000}
    matches = {day: [] for day in sessions}
    all_keys = set()
    scanned = 0
    pages = 0
    while pages < MAX_S3_PAGES:
        result = s3.list_object_versions(**args)
        pages += 1
        for row in result.get("Versions", []):
            scanned += 1
            key = str(row.get("Key", ""))
            all_keys.add(key)
            if not row.get("IsLatest") or not row.get("VersionId"):
                continue
            for day in sessions:
                if day in key and len(matches[day]) < 100:
                    matches[day].append({
                        "key": key, "versioned": row.get("VersionId") != "null",
                        "is_latest":True,
                    })
        if not result.get("IsTruncated"):
            return {
                "status":"COMPLETE_PREFIX_INVENTORY_NOT_LEDGER_ATTESTATION",
                "pages":pages,"versions_scanned":scanned,
                "keys_seen":len(all_keys),"matches_by_session":matches,
            }
        if not (result.get("NextKeyMarker") and result.get("NextVersionIdMarker")):
            return {
                "status":"PAGINATION_INCOMPLETE_UNVERIFIED",
                "pages":pages, "matches_by_session":matches,
            }
        args["KeyMarker"]=result["NextKeyMarker"]
        args["VersionIdMarker"]=result["NextVersionIdMarker"]
    return {
        "status":"INVENTORY_LIMIT_REACHED_UNVERIFIED",
        "pages":pages,"matches_by_session":matches,
    }


def alarms_snapshot(cw):
    alarms=[]
    token=None
    for _ in range(5):
        query={"AlarmNamePrefix":ST_ALARM_PREFIX,"MaxRecords":100}
        if token:query["NextToken"]=token
        resp=cw.describe_alarms(**query)
        for a in resp.get("MetricAlarms", []):
            alarms.append({
                "name":a.get("AlarmName"),
                "state":a.get("StateValue"),
                "namespace":a.get("Namespace"),
            })
        token=resp.get("NextToken")
        if not token:
            return {
                "status":"READ_ONLY_ALARMS_SNAPSHOT",
                "total":len(alarms),
                "non_ok":[a for a in alarms if a["state"] != "OK"],
                "all_ok": bool(alarms) and all(a["state"] == "OK" for a in alarms),
            }
    return {"status":"ALARM_PAGINATION_INCOMPLETE_UNVERIFIED",
            "total_seen":len(alarms),"all_ok":False}


def log_markers(logs, group, start_ms):
    events=[]
    next_token=None
    for page in range(MAX_LOG_PAGES):
        query={"logGroupName": group, "startTime": start_ms,
               "limit":LIMIT_LOG}
        if next_token:query["nextToken"]=next_token
        resp=logs.filter_log_events(**query)
        for e in resp.get("events", []):
            raw=e.get("message", "")
            matched=[m for m in ISSUES if m in raw]
            if matched:
                events.append({
                    "utc":datetime.fromtimestamp(
                        int(e["timestamp"])/1000,timezone.utc).isoformat(),
                    "markers": matched,
                })
        incoming=resp.get("nextToken")
        if not incoming or incoming==next_token:
            return {"status":"LOG_WINDOW_SEARCH_COMPLETE","pages":page+1,
                    "error_marker_count":len(events),
                    "last_error_markers":events[-10:]}
        next_token=incoming
    return {"status":"LOG_SEARCH_PAGE_LIMIT_UNVERIFIED","pages":MAX_LOG_PAGES,
            "error_marker_count_at_least":len(events),
            "last_error_markers":events[-10:]}


def inspect(c, dates, *, now=None):
    now=now or datetime.now(timezone.utc)
    require(all(re.fullmatch(r"\d{4}-\d{2}-\d{2}", d) for d in dates),
            "INVALID_SESSION_DATE_FORMAT")
    require(len(dates) == len(set(dates)) and 1 <= len(dates) <= 4,
            "SESSION_DATE_COUNT_INVALID")
    # Release inspection validates AWS account, exact 5 code hashes,
    # PROD disabled, ST EventBridge rule states & targets and CFN drift.
    base=release.check_readonly(c)
    require(base.get("current_all_candidate") is True and
            base.get("mixed_or_partial_code") is False and
            base.get("prod_schedules_all_disabled") is True and
            base.get("blocked_cfn_change_set",{}).get("status") ==
            "RETIRED_NOT_EXECUTED",
            "ST_RELEASE_NOT_FULLY_VERIFIED")
    s3=c["s3"]
    require(s3.get_bucket_versioning(Bucket=BUCKET).get("Status") == "Enabled",
            "ST_BUCKET_VERSIONING_NOT_ENABLED")
    head={day:{name:s3_head(s3,key) for name,key in S3_KEYS(day).items()}
          for day in dates}
    try:
        inventory=paper_version_inventory(s3, dates)
    except Exception as exc:
        inventory={"status":"INVENTORY_UNAVAILABLE_UNVERIFIED",
                   "reason":str(exc)[:160]}
    try:
        alarm=alarms_snapshot(c["cloudwatch"])
    except Exception as exc:
        alarm={"status":"ALARM_READ_UNAVAILABLE_UNVERIFIED",
               "reason":str(exc)[:160],"all_ok":False}
    start_ms=int((now-timedelta(hours=36)).timestamp()*1000)
    logs={}
    for group,name in ((WATCHDOG_GROUP,"watchdog"),(PAPER_GROUP,"paper")):
        try:logs[name]=log_markers(c["logs"],group,start_ms)
        except Exception as exc:
            logs[name]={"status":"LOG_READ_UNAVAILABLE_UNVERIFIED",
                        "reason":str(exc)[:160]}
    return {
        "kind":"STOCKLENS_ST_AFTERDEPLOY_FORENSICS_READ_ONLY",
        "checked_utc":now.isoformat(),
        "sessions_checked":dates,
        "release":{
            "all_five_candidate":base["current_all_candidate"],
            "mixed_or_partial_code":base["mixed_or_partial_code"],
            "dangerous_change_set":base["blocked_cfn_change_set"]["status"],
            "prod_schedules_all_disabled":base["prod_schedules_all_disabled"],
            "st_rule_targets_verified":base["st_rule_targets_verified"],
            "cfn_drift_requires_reconciliation":True,
        },
        "versioned_s3_head_probes":head,
        "paper_prefix_inventory":inventory,
        "alarms":alarm,
        "recent_log_marker_evidence":logs,
        # No amount of object-name or log evidence proves a qualified chain.
        "paper_ledger_acceptance":"NOT_PROVEN_BY_THIS_READ_ONLY_DIAGNOSTIC",
        "missing_sessions_are_not_replayed":True,
        "aws_mutations":False,"lambda_invocations":False,
        "broker_orders":False,"paper_backfill":False,
        "next_gate":"INDEPENDENT_RECEIPT_CHAIN_AND_CONTINUITY_ATTESTATION",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--sessions",nargs="+",default=["2026-11-05","2026-11-06"])
    args=p.parse_args()
    import boto3
    session=boto3.session.Session(region_name=release.REGION)
    clients={k:session.client(k) for k in
             ("sts","cloudformation","events","lambda","s3","cloudwatch","logs")}
    try:report=inspect(clients,args.sessions)
    except Exception as exc:
        report={"kind":"STOCKLENS_ST_AFTERDEPLOY_FORENSICS_READ_ONLY",
                "status":"BLOCKED",
                "reason":str(exc)[:220],
                "aws_mutations":False,"broker_orders":False,
                "paper_backfill":False}
        print(json.dumps(report,indent=2,sort_keys=True))
        return 2
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    raise SystemExit(main())

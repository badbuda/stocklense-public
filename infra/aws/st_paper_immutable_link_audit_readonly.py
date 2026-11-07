#!/usr/bin/env python3
"""ST Paper immutable chain comparison and deployed private contract — READ ONLY.

Only compare on-disk versioned JSON content by exact S3 version ID and pinned
deployed Lambda source. No mutation, code disclosure, portfolio dollar values,
trades, broker calls, simulated backfills or alarms reset. A matching hash pointer
alone does NOT prove economic accounting, exchange-calendar continuity or a
legitimate prospective restart.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys

from infra.aws import st_paper_chain_break_review_readonly as original
from infra.aws import st_paper_weekend_direct_guarded_release as release

ACCOUNT = release.ACCOUNT
BUCKET = original.BUCKET
BOOK = original.BOOK
SESSIONS = original.EXPECTED
PAIRS = [("2026-10-30","2026-11-02"),
         ("2026-11-02","2026-11-03"),
         ("2026-11-03","2026-11-04")]
MAX_BYTES = 2_000_000


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def stable_object(s3, key):
    try:
        meta = s3.head_object(Bucket=BUCKET, Key=key)
    except Exception as exc:
        code = str((getattr(exc,"response",{}) or {}).get("Error",{}).get("Code",""))
        if code in ("404","NotFound","NoSuchKey"):
            return None
        raise RuntimeError("HEAD_FAILED_NOT_A_404:"+key+":"+code) from exc
    version = meta.get("VersionId")
    size = meta.get("ContentLength")
    require(isinstance(version,str) and version not in ("", "null") and
            type(size) is int and 2 <= size <= MAX_BYTES,
            "UNVERSIONED_OR_OVERSIZE:" + key)
    obj = s3.get_object(Bucket=BUCKET,Key=key,VersionId=version)
    require(obj.get("VersionId")==version,"GET_VERSION_NOT_PINNED:"+key)
    raw=obj["Body"].read(MAX_BYTES+1)
    require(len(raw)==size,"S3_RECEIPT_BODY_SIZE_DIFFERS:"+key)
    try:
        payload=json.loads(raw)
    except (ValueError,UnicodeDecodeError) as exc:
        raise RuntimeError("RECEIPT_NOT_JSON:"+key) from exc
    require(isinstance(payload,dict),"RECEIPT_NOT_OBJECT:"+key)
    return {
        "payload":payload, "sha":hashlib.sha256(raw).hexdigest(),
        "version":version,"key":key,
    }


def compare_hash(pointer, expected):
    if not isinstance(pointer,str) or not re.fullmatch(r"[0-9a-f]{64}",pointer):
        return "MISSING_OR_INVALID_POINTER"
    return "MATCH" if pointer == expected else "DOES_NOT_MATCH_EXACT_STORED_BYTES"


def compare_identity(v, expected):
    return "MATCH" if v == expected else "MISMATCH"


def chain_report(s3):
    require(s3.get_bucket_versioning(Bucket=BUCKET).get("Status")=="Enabled",
            "ST_BUCKET_VERSIONING_DISABLED")
    genesis=stable_object(s3,f"paper/book/{BOOK}/genesis.json")
    require(genesis is not None,"GENESIS_MISSING")
    records={}
    summary={}
    for d in SESSIONS:
        records[d]={}
        summary[d]={}
        for kind in ("sessions","continuity"):
            item=stable_object(s3,f"paper/{kind}/{d}.json")
            records[d][kind]=item
            if item is None:
                summary[d][kind]="MISSING"
                continue
            p=item["payload"]
            report={"status":"IMMUTABLE_VERSIONED_OBJECT_PRESENT",
                    "session_field":compare_identity(p.get("session"),d),
                    "book_field":compare_identity(p.get("book"),BOOK),
                    "versioned":True}
            if kind=="sessions":
                report["broker_orders_authorized_false"]=p.get("broker_orders_authorized") is False
                report["broker_fills_observed_false"]=p.get("broker_fills_observed") is False
                report["shadow_mode"]=compare_identity(p.get("mode"),
                                                        "SHADOW_ONLY_NO_BROKER_ACTIONS")
                st=p.get("state")
                if isinstance(st,dict):
                    report["state_last_mark_session"]=compare_identity(
                        st.get("last_mark_session"),d)
            else:
                report["continuity_status"]=p.get("status")
                report["broker_orders_false"]=p.get("broker_orders") is False
                report["broker_fills_false"]=p.get("broker_fills") is False
                evidence=p.get("evidence")
                if isinstance(evidence,dict):
                    paper=records[d].get("sessions")
                    if paper is not None:
                        report["paper_hash_attested"]=compare_hash(
                            evidence.get("paper_sha256"),paper["sha"])
                        report["paper_key_attested"]=compare_identity(
                            evidence.get("paper_key"),paper["key"])
                        report["paper_version_attested"]=compare_identity(
                            evidence.get("paper_version_id"),paper["version"])
                report["qualified_in_record"]=p.get("status") in (
                    "ON_TIME_QUALIFIED","LATE_WITH_CONTEMPORANEOUS_EVIDENCE")
            summary[d][kind]=report

    bootstrap=records["2026-10-30"]
    gp=genesis["payload"]
    genesis_review={
        "status":"VERSIONED_GENESIS_PRESENT",
        "book_matches":compare_identity(gp.get("book"),BOOK),
        "initial_paper_link":(
            compare_hash(gp.get("receipt_sha256"),bootstrap["sessions"]["sha"])
            if bootstrap["sessions"] is not None else "INITIAL_PAPER_MISSING"),
        "initial_continuity_link":(
            compare_hash(gp.get("continuity_sha256"),bootstrap["continuity"]["sha"])
            if bootstrap["continuity"] is not None else "INITIAL_CONTINUITY_MISSING"),
    }
    link_checks=[]
    for a,b in PAIRS:
        older=records[a]; newer=records[b]
        require(older["sessions"] is not None and older["continuity"] is not None and
                newer["sessions"] is not None and newer["continuity"] is not None,
                "ORIGINAL_CHAIN_PAIR_MISSING:"+a+":"+b)
        link_checks.append({
            "previous_session":a,"session":b,
            "paper_prior_receipt_link":compare_hash(
                newer["sessions"]["payload"].get("prior_receipt_sha256"),
                older["sessions"]["sha"]),
            "continuity_previous_record_link":compare_hash(
                newer["continuity"]["payload"].get("previous_record_sha256"),
                older["continuity"]["sha"]),
        })
    return {
        "genesis":genesis_review,
        "versioned_daily_records":summary,
        "stored_hash_linkage":link_checks,
        "missing_dates": [d for d in SESSIONS if
                          any(records[d][k] is None for k in ("sessions","continuity"))],
        "original_economic_accounting_status":"NOT_ATTESTED_BY_HASH_LINKS",
        "no_broker_or_historical_backfill":True,
    }


def inspect(c):
    base=release.check_readonly(c)
    require(base.get("current_all_candidate") is True and
            base.get("mixed_or_partial_code") is False and
            base.get("prod_schedules_all_disabled") is True and
            base.get("blocked_cfn_change_set",{}).get("status")==
            "RETIRED_NOT_EXECUTED",
            "RELEASE_AUTHORITY_NOT_VERIFIED")
    records=chain_report(c["s3"])
    state,configs,targets=release.trusted_inventory(c)
    fn=state["st_outputs"]["CandidatePaperFunctionName"]
    try:
        contract=original.inspect_private_contract(c["lambda"],fn)
    except Exception as exc:
        contract={
            "status":"PRIVATE_RUNTIME_AST_UNVERIFIED",
            "reason_type":type(exc).__name__,
            "source_disclosed":False,
        }
    return {
        "kind":"STOCKLENS_ST_IMMUTABLE_CHAIN_LINK_REVIEW_READ_ONLY",
        "release_sha_verified":True,
        "prod_schedules_all_disabled":True,
        "st_schedule_targets_verified":targets,
        "private_runtime_contract":contract,
        "record_chain":records,
        "forward_epoch_transition":"NOT_AUTHORIZED_OR_IMPLEMENTED",
        "requires_operator_review_before_mutation":True,
        "aws_mutations":False,
        "lambda_invocations":False,
        "broker_orders":False,
        "paper_backfill":False,
    }


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--review",action="store_true")
    args=parser.parse_args()
    require(args.review,"RUN_WITH_--review")
    import boto3
    session=boto3.session.Session(region_name=release.REGION)
    c={name:session.client(name) for name in
       ("sts","s3","cloudformation","events","lambda")}
    report=inspect(c)
    print(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status":"BLOCKED_NO_MUTATIONS",
                          "error_type":type(exc).__name__,
                          "reason":str(exc)[:170],
                          "aws_mutations":False,"broker_orders":False,
                          "lambda_invocations":False,"paper_backfill":False}))
        raise SystemExit(2)

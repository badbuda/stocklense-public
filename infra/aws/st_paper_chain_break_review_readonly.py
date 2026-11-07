#!/usr/bin/env python3
"""ST Paper break review. ONLY authenticated read-only AWS calls.

Reads the exact immutable Paper/Continuity/Genesis receipts through 2026-11-06,
outputs field-name schemas and hashes (not holdings, cash, P&L, fills or raw
records), and checks the deployed private handler source by pinned Git-blob SHA
IN MEMORY. No private source is printed, persisted, uploaded or logged.

This does NOT recover missed sessions, invoke Lambda, rebuild trading records,
suppress alarms, change CloudFormation, or certify the book's economic validity.
The purpose is to design a safe forward-only epoch, if required, from the
contract actually deployed rather than assuming a public repository file.
"""
from __future__ import annotations

import ast
import argparse
import base64
import hashlib
import io
import json
import re
import sys
from urllib.request import urlopen
import zipfile

from infra.aws import st_paper_weekend_direct_guarded_release as release

ST = release.ST
BUCKET = release.p.ST_BUCKET
BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK"
EXPECTED = (
    "2026-10-30",
    "2026-11-02",
    "2026-11-03",
    "2026-11-04",
    "2026-11-05",
    "2026-11-06",
)
MAX_JSON = 2_000_000
MAX_PACKAGE = release.p.ZIP_SIZE_LIMIT
PAYLOAD_KEYS = (
    "session", "session_date", "expected_session", "prior_session",
    "previous_session", "genesis_session", "last_session", "asof_date",
    "continuity_status", "status", "book", "book_id", "mode",
)
HASH_KEYS = (
    "sha256", "previous_sha256", "prior_sha256", "parent_sha256",
    "previous_receipt_sha256", "receipt_sha256", "paper_sha256",
    "previous_hash", "prior_hash", "parent_hash", "hash",
)
SOURCE_MARKERS = (
    "STAGING_PAPER_SCHEDULE_READINESS", "STAGING_PAPER_ONLY",
    "STAGING_PAPER_BOOTSTRAP_PREFLIGHT",
    "SESSION_WITHOUT_CONTINUITY_RECORD",
    "ON_TIME_QUALIFIED", "LATE_WITH_CONTEMPORANEOUS_EVIDENCE",
    "paper/continuity/", "paper/sessions/", "paper/book/",
)
INTERESTING = (
    "book","paper","session","continuity","receipt","genesis",
    "readiness","watchdog","handler","bootstrap","previous",
)


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def keys_only(value):
    if not isinstance(value, dict):
        return {"type":type(value).__name__}
    names=sorted(str(x) for x in value)
    result={"type":"object", "field_count":len(names),
            "fields":names[:70]}
    nested={}
    for name in names:
        if name in value and isinstance(value[name],dict):
            nested[name]=sorted(str(k) for k in value[name])[:40]
    if nested: result["nested_fields"]=dict(list(nested.items())[:15])
    return result


def safe_fields(payload):
    if not isinstance(payload, dict):
        return {}
    output={}
    for name in PAYLOAD_KEYS:
        value=payload.get(name)
        if isinstance(value,str) and len(value)<85 and re.fullmatch(
                r"[A-Za-z0-9_.:-]+",value):
            output[name]=value
    for name in HASH_KEYS:
        value=payload.get(name)
        if isinstance(value,str) and re.fullmatch(r"[0-9a-f]{64}",value):
            output[name]=value
    return output


def receipt(s3,key):
    try:
        meta=s3.head_object(Bucket=BUCKET,Key=key)
    except Exception as e:
        error=(getattr(e,"response",{}) or {}).get("Error",{})
        code=str(error.get("Code",""))
        if code in ("404","NoSuchKey","NotFound"):
            return {"status":"MISSING_VERIFIED_S3_KEY"}
        raise RuntimeError("S3_RECEIPT_HEAD_FAILED:" + key + ":" +
                           (code or type(e).__name__)) from e
    version=meta.get("VersionId")
    require(isinstance(version,str) and version not in ("null",""),
            "UNVERSIONED_RECEIPT:" + key)
    size=meta.get("ContentLength")
    require(type(size) is int and 2 <= size <= MAX_JSON,
            "RECEIPT_SIZE_UNEXPECTED:" + key)
    obj=s3.get_object(Bucket=BUCKET,Key=key,VersionId=version)
    require(obj.get("VersionId")==version,
            "RECEIPT_S3_VERSION_DRIFT:" + key)
    raw=obj["Body"].read(MAX_JSON + 1)
    require(len(raw)==size,
            "RECEIPT_BODY_LENGTH_MISMATCH:" + key)
    try: payload=json.loads(raw)
    except ValueError as exc:
        raise RuntimeError("RECEIPT_JSON_INVALID:"+key) from exc
    return {
        "status":"VERSIONED_JSON_READ_NOT_LEDGER_ACCEPTANCE",
        "bytes":size,
        "s3_version_verified":True,
        "sha256":hashlib.sha256(raw).hexdigest(),
        "schema":keys_only(payload),
        "safe_identifiers":safe_fields(payload),
    }


def sha256_b64(raw):
    return base64.b64encode(hashlib.sha256(raw).digest()).decode()


def private_contract_from_zip(data):
    require(sha256_b64(data)==release.NEW,
            "PRIVATE_RUNTIME_ARCHIVE_SHA_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        name=release.p.ENTRY_PATH
        require(name in z.namelist(),
                "PRIVATE_ENTRYPOINT_MODULE_MISSING")
        source=z.read(name)
        require(len(source)<=release.p.MODULE_SIZE_LIMIT and
                release.p.git_blob_sha(source)==release.p.ENTRY_BLOB,
                "PRIVATE_HANDLER_GIT_BLOB_UNVERIFIED")
        tree=ast.parse(source)
        constants={node.value for node in ast.walk(tree)
                   if isinstance(node,ast.Constant) and
                   isinstance(node.value,str)}
        # No private code, literals, secrets, docstrings or variable values
        # are emitted. Only a narrow published vocabulary is used here.
        fn_names=[
            node.name for node in tree.body
            if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef))
            and any(term in node.name.lower() for term in INTERESTING)
        ]
        modes={m: m in constants for m in SOURCE_MARKERS}
        return {
            "status":"PINNED_PRIVATE_HANDLER_AST_READ_IN_MEMORY",
            "entrypoint_blob_verified":True,
            "engine_patched_code_sha_verified":True,
            "selected_function_names":fn_names[:35],
            "known_mode_and_guard_literals_present":modes,
            "source_content_disclosed":False,
            "private_source_persisted":False,
            "note":"Static AST is not proof of runtime guard behavior.",
        }


def inspect_private_contract(lam, name):
    fn=lam.get_function(FunctionName=name)
    cfg=fn.get("Configuration",{})
    require(cfg.get("CodeSha256")==release.NEW and
            cfg.get("FunctionName")==name,
            "ST_DEPLOYED_PAPER_CODE_SHA_MISMATCH")
    url=fn.get("Code",{}).get("Location")
    require(isinstance(url,str) and url.startswith("https://"),
            "PRIVATE_ZIP_SIGNED_URL_UNAVAILABLE")
    with urlopen(url,timeout=40) as response:
        binary=response.read(MAX_PACKAGE+1)
    require(len(binary)<=MAX_PACKAGE, "PRIVATE_PACKAGE_TOO_LARGE")
    return private_contract_from_zip(binary)


def inspect(c):
    baseline=release.check_readonly(c)
    require(baseline.get("current_all_candidate") is True and
            baseline.get("mixed_or_partial_code") is False and
            baseline.get("prod_schedules_all_disabled") is True and
            baseline.get("blocked_cfn_change_set",{}).get("status")==
            "RETIRED_NOT_EXECUTED",
            "POST_DEPLOY_SECURITY_BASELINE_NOT_VERIFIED")
    s3=c["s3"]
    require(s3.get_bucket_versioning(Bucket=BUCKET).get("Status")=="Enabled",
            "S3_ST_BUCKET_NOT_VERSIONED")
    snap={
        "genesis":receipt(s3,f"paper/book/{BOOK}/genesis.json"),
        "sessions":{},
        "continuity":{},
    }
    for day in EXPECTED:
        snap["sessions"][day]=receipt(s3,f"paper/sessions/{day}.json")
        snap["continuity"][day]=receipt(s3,f"paper/continuity/{day}.json")
    release_state,_configs,_targets=release.trusted_inventory(c)
    fn=release_state["st_outputs"]["CandidatePaperFunctionName"]
    try:
        contract=inspect_private_contract(c["lambda"],fn)
    except Exception as exc:
        contract={"status":"PRIVATE_HANDLER_CONTRACT_UNVERIFIED",
                  "reason":str(exc)[:150],
                  "source_content_disclosed":False}
    missing={
        day:[part for part in ("sessions","continuity") if
             snap[part][day]["status"]=="MISSING_VERIFIED_S3_KEY"]
        for day in EXPECTED
    }
    return {
        "kind":"STOCKLENS_ST_PAPER_CHAIN_BREAK_REVIEW_READ_ONLY",
        "confirmed_code_release":True,
        "private_runtime_contract":contract,
        "receipt_headers_and_schemas":snap,
        "missing_by_date":{day:parts for day,parts in missing.items() if parts},
        "known_gap_needs_explicit_policy":bool(missing["2026-11-05"]),
        "latest_qualified_Paper_book":"NOT_ATTESTED_FROM_STRUCTURAL_READS",
        "safe_forward_recovery":"REQUIRES_EXPLICIT_REVIEWED_NEW_EPOCH_OR_CONTEMPORANEOUS_EVIDENCE",
        "old_epoch_is_not_writable_by_this_tool":True,
        "aws_mutations":False,
        "lambda_invocations":False,
        "broker_orders":False,
        "paper_backfill":False,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--review",action="store_true")
    args=ap.parse_args()
    require(args.review,"RUN_WITH_--review_READONLY_ONLY")
    import boto3
    session=boto3.session.Session(region_name=release.REGION)
    clients={n:session.client(n) for n in
             ("sts","lambda","events","cloudformation","s3")}
    result=inspect(clients)
    print(json.dumps(result,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"status":"BLOCKED_NO_MUTATIONS",
                          "reason":str(exc)[:220],
                          "aws_mutations":False,"lambda_invocations":False,
                          "broker_orders":False,"paper_backfill":False}))
        raise SystemExit(2)

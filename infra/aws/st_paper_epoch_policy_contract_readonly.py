#!/usr/bin/env python3
"""Read-only map of ST's ACTUAL deployed paper/monitoring gap-policy contracts.

No Lambda invoke, no code changes, no S3 writes, no broker and NO private
source disclosure. The verified private ZIP is parsed entirely in memory and
only a strict, preapproved status/field vocabulary and selected call edges are
reported. The report DOES NOT authorize a new epoch, missed-day marker, or
claim that an implementation safely supports these mechanisms.

Use this before proposing any 2026-11-05/06 gap policy change.
"""
from __future__ import annotations

import ast
import json
import re
import sys
import argparse
from datetime import datetime, timezone

from infra.aws import st_paper_chain_break_review_readonly as private
from infra.aws import st_paper_weekend_direct_guarded_release as release

REGION=release.REGION
ACCOUNT=release.ACCOUNT
ST=release.ST

SAFE_FN_NAMES={
    "handler", "run_paper", "run_paper_catchup",
    "run_scheduled_paper", "verify_book_chain",
    "_read_genesis", "_read_continuity", "_write_continuity",
    "build_paper_receipt", "audit_paper_schedule_readiness",
    "preflight_prospective_paper_bootstrap",
    "preflight_handler", "previous_xnys_session",
    "watchdog", "monitor", "audit", "inspect",
    "verify_continuity", "verify_session",
    "classify_session", "classify_continuity",
    "expected_sessions", "expected_exchange_sessions",
    "_continuity_key", "_read_receipt", "_write_receipt",
}

SAFE_LITERALS={
    "MISSED_UNRECOVERABLE", "RECONSTRUCTED_ACCOUNTING_ONLY",
    "ON_TIME_QUALIFIED", "LATE_WITH_CONTEMPORANEOUS_EVIDENCE",
    "SESSION_WITHOUT_CONTINUITY_RECORD", "STAGING_PAPER_ONLY",
    "STAGING_PAPER_SCHEDULE_READINESS", "STAGING_PAPER_BOOTSTRAP_PREFLIGHT",
    "BOOK_HALTED", "HALTED", "FAIL_CLOSED", "NO_BROKER",
    "PAPER_BOOK_AHEAD_OF_PREVIOUS_SIGNAL",
    "MISSED_NO_BACKFILL", "MISSED_SESSION_RECORDED_NO_BACKFILL",
    "STAGED_PAPER_VERIFIED", "STAGING_PAPER_SCHEDULE_READINESS_PASS_READ_ONLY",
    "epoch", "qualified_streak_in_epoch", "previous_record_sha256",
    "prior_receipt_sha256", "paper/continuity/", "paper/sessions/",
    "paper/book/", "bootstrap", "expected_session",
    "MonitoringStartSession", "STOCKLENS_MONITORING_START_SESSION",
}

SAFE_MODULES={
    "infra.aws.independent_paper", "infra.aws.independent_watchdog",
    "infra.aws.independent_signal", "stocklens.paper",
}

def require(ok,msg):
    if not ok:raise RuntimeError(msg)


def ast_summary(source:bytes, module:str):
    require(module in SAFE_MODULES,"PRIVATE_MODULE_NOT_ALLOWLISTED")
    require(len(source)<=1_500_000,"PRIVATE_MODULE_OVERSIZE")
    tree=ast.parse(source,filename="<private-read-only>",mode="exec")
    functions=[]
    imports=[]
    for stmt in tree.body:
        if isinstance(stmt,ast.ImportFrom):
            if stmt.module in SAFE_MODULES:
                imports.append(stmt.module)
        if isinstance(stmt,(ast.FunctionDef,ast.AsyncFunctionDef)) and stmt.name in SAFE_FN_NAMES:
            literals={x.value for x in ast.walk(stmt)
                      if isinstance(x,ast.Constant) and
                      isinstance(x.value,str) and x.value in SAFE_LITERALS}
            direct_calls=set()
            for node in ast.walk(stmt):
                if not isinstance(node,ast.Call):
                    continue
                target=node.func
                if isinstance(target,ast.Name) and target.id in SAFE_FN_NAMES:
                    direct_calls.add(target.id)
            functions.append({
                "name":stmt.name,
                "visible_known_statuses_or_fields":sorted(literals),
                "direct_calls_to_known_contract_functions":sorted(direct_calls),
                "function_has_explicit_raise":any(isinstance(x,ast.Raise)
                                                  for x in ast.walk(stmt)),
                "source_lines_disclosed":False,
            })
    all_known_literals={x.value for x in ast.walk(tree)
                        if isinstance(x,ast.Constant) and
                        isinstance(x.value,str) and x.value in SAFE_LITERALS}
    has_handler=any(isinstance(x,(ast.FunctionDef,ast.AsyncFunctionDef)) and
                    x.name=="handler" for x in tree.body)
    return {
        "module":module,
        "handler_function_present":has_handler,
        "allowed_known_imports":sorted(set(imports)),
        "module_known_literal_vocabulary":sorted(all_known_literals),
        "selected_functions":functions,
        "static_contract_only":True,
        "private_source_printed":False,
    }


def contracts_from_verified_archive(data:bytes, expected_modules:list[str]):
    require(private.sha256_b64(data)==release.NEW,"DEPLOYED_ARCHIVE_SHA_MISMATCH")
    import io
    import zipfile
    modules={}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files=set(z.namelist())
        require(len(files)==len(z.namelist()),"PRIVATE_ARCHIVE_DUPLICATE_MEMBERS")
        for module in expected_modules:
            require(module in SAFE_MODULES,"UNAUTHORIZED_MODULE_REQUEST")
            path=module.replace(".","/")+".py"
            if path not in files:
                modules[module]={"status":"MODULE_NOT_IN_RELEASE_ARCHIVE_UNVERIFIED"}
                continue
            raw=z.read(path)
            if module=="infra.aws.independent_paper":
                require(release.p.git_blob_sha(raw)==release.p.ENTRY_BLOB,
                        "DEPLOYED_PRIVATE_PAPER_HANDLER_BLOB_MISMATCH")
            modules[module]={"status":"VERIFIED_PACKAGE_PRIVATE_AST_SUMMARY",
                             **ast_summary(raw,module)}
    return modules


def inspect(services):
    baseline=release.check_readonly(services)
    require(baseline.get("current_all_candidate") is True and
            baseline.get("mixed_or_partial_code") is False and
            baseline.get("prod_schedules_all_disabled") is True and
            baseline.get("blocked_cfn_change_set",{}).get("status")=="RETIRED_NOT_EXECUTED",
            "EXPECTED_VERIFIED_ST_RELEASE_MISSING")
    state,cfg,_=release.trusted_inventory(services)
    paper=state["st_outputs"]["CandidatePaperFunctionName"]
    watchdog=state["st_outputs"]["CandidateSessionWatchdogFunctionName"]
    require(cfg[paper]["CodeSha256"]==release.NEW and
            cfg[watchdog]["CodeSha256"]==release.NEW,
            "ST_PAPER_WATCHDOG_PACKAGE_MISMATCH")
    fn=services["lambda"].get_function(FunctionName=paper)
    require(fn["Configuration"]["CodeSha256"]==release.NEW,
            "ST_PAPER_ZIP_NOT_PINNED")
    location=fn["Code"].get("Location")
    require(isinstance(location,str) and location.startswith("https://"),
            "PRIVATE_SIGNED_URL_MISSING")
    from urllib.request import urlopen
    with urlopen(location,timeout=40) as response:
        archive=response.read(release.p.ZIP_SIZE_LIMIT+1)
    require(len(archive)<=release.p.ZIP_SIZE_LIMIT,
            "PRIVATE_RUNTIME_ZIP_OVERSIZE")
    watchdog_handler=cfg[watchdog].get("Handler","")
    require(re.fullmatch(r"[A-Za-z0-9_.]+",watchdog_handler) is not None and
            watchdog_handler.endswith(".handler"),"UNKNOWN_WATCHDOG_HANDLER_REFERENCE")
    watchdog_module=watchdog_handler.rsplit(".",1)[0]
    # Never inspect modules outside explicitly reviewed, non-secret allowlist.
    require(watchdog_module in SAFE_MODULES,
            "UNKNOWN_PRIVATE_WATCHDOG_MODULE_REQUIRES_REVIEW")
    expected_modules=list(dict.fromkeys(
        ["infra.aws.independent_paper",watchdog_module]))
    modules=contracts_from_verified_archive(archive,expected_modules)
    return {
        "kind":"STOCKLENS_ST_EPOCH_GAP_POLICY_CONTRACT_READ_ONLY",
        "reviewed_utc":datetime.now(timezone.utc).isoformat(),
        "all_five_st_new_code_verified":True,
        "prod_schedules_all_disabled":True,
        "original_nov05_nov06_paper_missing":True,
        "private_handler_modules":modules,
        "governance": {
            "source_disclosed":False,"private_archive_persisted":False,
            "lambda_invoked":False,"aws_mutations":False,"broker_orders":False,
            "historical_paper_backfill":False,
            "new_epoch_authorized":False,
            "static_ast_does_not_certify_runtime_gap_policy":True,
        },
        "next_gate":"DEMONSTRATE_EXACT_PAPER_AND_WATCHDOG_POLICY_FOR_MISSED_DAYS_AND_NEW_EPOCH",
    }


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--review",action="store_true")
    args=p.parse_args()
    require(args.review,"EXPLICIT_--review_REQUIRED")
    import boto3
    session=boto3.session.Session(region_name=REGION)
    clients={x:session.client(x) for x in
             ("sts","lambda","cloudformation","events")}
    report=inspect(clients)
    print(json.dumps(report,indent=2,sort_keys=True))
    return 0


if __name__=="__main__":
    try:raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({
            "status":"BLOCKED_READ_ONLY","reason_type":type(exc).__name__,
            "reason":str(exc)[:160],"aws_mutations":False,
            "lambda_invocations":False,"broker_orders":False,
            "historical_backfill":False
        }))
        raise SystemExit(2)

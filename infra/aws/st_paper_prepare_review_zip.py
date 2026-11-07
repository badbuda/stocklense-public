#!/usr/bin/env python3
"""Prepare, but NEVER deploy, an ST-only Paper Lambda engine patch.

This performs authenticated, read-only AWS provenance checks before constructing
a private local review artifact. No S3 writes, Lambda mutation/invocation,
CloudFormation change set, EventBridge mutation, alarm acknowledgement, broker
orders or historical Paper recreation. It refuses unknown deployed source blobs.
"""
from __future__ import annotations

import argparse
import ast
import base64
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import re
from urllib.request import urlopen
import zipfile

ACCOUNT = "634740393398"
REGION = "eu-central-1"
ST = "stocklens-st"
PROD = "stocklens-prod"
ST_BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
PROD_BUCKET = "stocklens-prod-candidatedata-c3yge4ymwb7u"
PAPER_FN = ST + "-paper-candidate"
ENTRY_PATH = "infra/aws/independent_paper.py"
PAPER_PATH = "stocklens/paper.py"
OLD_ENGINE_BLOB = "5058d7c84779dea0726b815bbd1f6c19d2582a63"
ENTRY_BLOB = "21ae6282f59fc97b493072ddd8863b506e4ff745"
NEW_ENGINE_BLOB = "ea8427b32899f713468f072dee80ee71216289bf"
FIXED_SOURCE_REF = "dcc6b49c5fdb17d4be4466f165849a55c4af6e67"
FIXED_SOURCE_URL = (
    "https://raw.githubusercontent.com/badbuda/stocklense-public/"
    + FIXED_SOURCE_REF + "/" + PAPER_PATH
)
ZIP_SIZE_LIMIT = 80_000_000
MODULE_SIZE_LIMIT = 1_000_000
RULES = ("CandidateSignalOnlyRuleName", "CandidatePaperOnlyRuleName",
         "CandidateOrchestratorRuleName")


def require(ok, why):
    if not ok:
        raise RuntimeError(why)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def sha256_b64(data: bytes) -> str:
    return base64.b64encode(hashlib.sha256(data).digest()).decode()


def read_limited(stream, limit=ZIP_SIZE_LIMIT) -> bytes:
    blob = stream.read(limit + 1)
    require(len(blob) <= limit, "REMOTE_BLOB_EXCEEDS_LIMIT")
    return blob


def checked_sources(old_zip: bytes, fixed_engine: bytes, current_code_sha: str):
    require(sha256_b64(old_zip) == current_code_sha,
            "DEPLOYED_ZIP_NOT_SAME_AS_LAMBDA_CODE_SHA")
    require(git_blob_sha(fixed_engine) == NEW_ENGINE_BLOB,
            "NEW_ENGINE_PINNED_SOURCE_HASH_MISMATCH")
    with zipfile.ZipFile(io.BytesIO(old_zip)) as original:
        infos = original.infolist()
        names = [info.filename for info in infos]
        require(len(names) == len(set(names)), "DUPLICATE_ZIP_PATHS")
        require(PAPER_PATH in names and ENTRY_PATH in names, "PAPER_RUNTIME_MODULE_MISSING")
        paper_info, entry_info = original.getinfo(PAPER_PATH), original.getinfo(ENTRY_PATH)
        require(0 < paper_info.file_size <= MODULE_SIZE_LIMIT and
                0 < entry_info.file_size <= MODULE_SIZE_LIMIT,
                "PAPER_MODULE_UNEXPECTED_SIZE")
        old_engine = original.read(PAPER_PATH)
        entrypoint = original.read(ENTRY_PATH)
        require(git_blob_sha(old_engine) == OLD_ENGINE_BLOB,
                "OLD_ENGINE_DIFFERS_FROM_AUDITED_ST_LAMBDA")
        require(git_blob_sha(entrypoint) == ENTRY_BLOB,
                "PRIVATE_HANDLER_DIFFERS_FROM_AUDITED_ST_LAMBDA")
        # Verify the public patch changes only the intended function bodies;
        # every other top-level declaration is preserved semantically.
        def fixed_ast_items(data):
            tree = ast.parse(data)
            return {
                getattr(node, "name", "line:" + str(i)): ast.dump(node)
                for i, node in enumerate(tree.body)
                if not (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                        and node.name in ("_fetch_intraday", "fetch_execution_market"))
            }
        require(fixed_ast_items(old_engine) == fixed_ast_items(fixed_engine),
                "UNEXPECTED_PAPER_STRATEGY_OR_ACCOUNTING_SOURCE_DIFF")
        return infos, old_engine, entrypoint


def build_review_archive(old_zip: bytes, fixed_engine: bytes, current_code_sha: str):
    infos, _old_engine, entrypoint = checked_sources(old_zip, fixed_engine, current_code_sha)
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(old_zip)) as old, zipfile.ZipFile(out, "w") as new:
        new.comment = old.comment
        for info in infos:
            require(info.file_size <= ZIP_SIZE_LIMIT, "OVERSIZED_ARCHIVE_MEMBER")
            data = fixed_engine if info.filename == PAPER_PATH else old.read(info.filename)
            new.writestr(info, data, compress_type=info.compress_type)
    patched = out.getvalue()
    require(len(patched) <= ZIP_SIZE_LIMIT, "PATCHED_ZIP_TOO_LARGE")
    with zipfile.ZipFile(io.BytesIO(old_zip)) as before, zipfile.ZipFile(io.BytesIO(patched)) as after:
        require(before.namelist() == after.namelist(), "ZIP_MEMBER_SET_OR_ORDER_CHANGED")
        changed = []
        for name in before.namelist():
            if before.read(name) != after.read(name):
                changed.append(name)
        require(changed == [PAPER_PATH], "UNEXPECTED_ZIP_MEMBER_CONTENT_CHANGE")
        require(git_blob_sha(after.read(ENTRY_PATH)) == ENTRY_BLOB,
                "PRIVATE_HANDLER_NOT_PRESERVED")
        require(git_blob_sha(after.read(PAPER_PATH)) == NEW_ENGINE_BLOB,
                "FIXED_ENGINE_NOT_VERIFIED")
    return patched, {"only_changed_member": PAPER_PATH,
                     "handler_preserved": True, "zip_members": len(infos),
                     "original_sha256_b64": current_code_sha,
                     "candidate_sha256_b64": sha256_b64(patched),
                     "entrypoint_git_blob": git_blob_sha(entrypoint),
                     "engine_git_blob": NEW_ENGINE_BLOB}


def outputs(cf, stack):
    row = cf.describe_stacks(StackName=stack).get("Stacks", [])
    require(len(row) == 1 and row[0].get("StackStatus") in
            ("CREATE_COMPLETE", "UPDATE_COMPLETE"),
            "UNSTABLE_STACK:" + stack)
    return row[0], {i["OutputKey"]: i["OutputValue"] for i in row[0].get("Outputs", [])}


def inspect_control_plane(clients):
    require(clients["sts"].get_caller_identity().get("Account") == ACCOUNT,
            "WRONG_AWS_ACCOUNT")
    st_row, st = outputs(clients["cloudformation"], ST)
    _, prod = outputs(clients["cloudformation"], PROD)
    require(st.get("CandidateDataBucket") == ST_BUCKET and
            prod.get("CandidateDataBucket") == PROD_BUCKET,
            "ST_PROD_BUCKET_ISOLATION_FAILED")
    require(st.get("CandidatePaperFunctionName") == PAPER_FN,
            "ST_PAPER_FUNCTION_OUTPUT_WRONG")
    states = {}
    for env, result in (("ST", st), ("PROD", prod)):
        for key in RULES:
            states[env + ":" + key] = clients["events"].describe_rule(
                Name=result[key]).get("State")
    require(states["ST:CandidateSignalOnlyRuleName"] == "ENABLED" and
            states["ST:CandidatePaperOnlyRuleName"] == "ENABLED" and
            states["ST:CandidateOrchestratorRuleName"] == "DISABLED",
            "UNEXPECTED_ST_SCHEDULE_STATES")
    require(all(states["PROD:" + key] == "DISABLED" for key in RULES),
            "PROD_SCHEDULE_ENABLED")
    artifact_params = {p["ParameterKey"]: p.get("ParameterValue", "")
                       for p in st_row.get("Parameters", [])}
    artifact_bucket = artifact_params.get("ArtifactBucket")
    artifact_key = artifact_params.get("ArtifactKey")
    require(bool(artifact_bucket) and bool(artifact_key)
            and not re.search(r"latest|current", artifact_key, re.I),
            "CFN_SOURCE_ARTIFACT_NOT_PINNED")
    paper = clients["lambda"].get_function(FunctionName=PAPER_FN)
    cfg = paper.get("Configuration", {})
    require(cfg.get("FunctionName") == PAPER_FN and
            cfg.get("State") == "Active" and
            cfg.get("LastUpdateStatus") == "Successful",
            "ST_PAPER_LAMBDA_NOT_READY")
    require(cfg.get("Handler") == "infra.aws.independent_paper.handler",
            "PAPER_HANDLER_CONTRACT_CHANGED")
    require(cfg.get("Environment", {}).get("Variables", {}).get("STOCKLENS_DATA_BUCKET")
            == ST_BUCKET, "PAPER_HANDLER_BUCKET_WRONG")
    require(not cfg.get("CodeSigningConfigArn"), "LAMBDA_CODESIGNING_REVIEW_REQUIRED")
    code_sha = cfg.get("CodeSha256")
    require(isinstance(code_sha, str) and len(code_sha) > 30, "LAMBDA_CODE_SHA_MISSING")
    # Read original CloudFormation artifact; never print bucket/key or source.
    metadata = clients["s3"].head_object(Bucket=artifact_bucket, Key=artifact_key)
    require(0 < metadata.get("ContentLength", -1) <= ZIP_SIZE_LIMIT,
            "CFN_ARTIFACT_UNEXPECTED_SIZE")
    stored = clients["s3"].get_object(Bucket=artifact_bucket, Key=artifact_key)
    source_zip = read_limited(stored["Body"])
    require(sha256_b64(source_zip) == code_sha, "CFN_ARTIFACT_DIFFERS_FROM_DEPLOYED_ST")
    # Keep an independently retrieved Lambda source integrity check.
    url = paper.get("Code", {}).get("Location")
    require(isinstance(url, str) and url.startswith("https://"),
            "LAMBDA_SIGNED_URL_MISSING")
    with urlopen(url, timeout=35) as remote:
        lambda_zip = read_limited(remote)
    require(sha256_b64(lambda_zip) == code_sha and
            hashlib.sha256(lambda_zip).digest() == hashlib.sha256(source_zip).digest(),
            "LAMBDA_ZIP_ARTIFACT_MISMATCH")
    signal_sha = clients["lambda"].get_function_configuration(
        FunctionName=st["CandidateFunctionName"]).get("CodeSha256")
    preflight_sha = clients["lambda"].get_function_configuration(
        FunctionName=st["CandidatePaperPreflightFunctionName"]).get("CodeSha256")
    params = {k: artifact_params.get(k) for k in
              ("CandidateSignalScheduleState", "ExpectedSchedulerState",
               "MonitoringStartSession")}
    # CloudFormation parameters still say DISABLED while EventBridge rules
    # are ENABLED. CFN deployment risks reverting schedules; do not apply.
    drift = params.get("CandidateSignalScheduleState") != states[
        "ST:CandidateSignalOnlyRuleName"]
    return lambda_zip, code_sha, {
        "cloudformation_artifact_matches_lambda": True,
        "cfn_schedule_parameter_vs_live_mismatch": drift,
        "cfn_monitoring_parameters": params,
        "st_signal_code_matches_paper": signal_sha == code_sha,
        "st_preflight_code_matches_paper": preflight_sha == code_sha,
        "st_rules": {k: states["ST:" + k] for k in RULES},
        "prod_schedules_all_disabled": True,
        "code_signing": "NOT_CONFIGURED",
        "lambda_configuration_verified": True,
        "aws_mutations": False,
        "broker_orders": False,
    }


def prepare_local_review_artifact(clients, fixed_engine: bytes, home: Path):
    old_zip, sha, control = inspect_control_plane(clients)
    candidate, proof = build_review_archive(old_zip, fixed_engine, sha)
    directory = home / ".stocklens-private-st-releases"
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(directory, 0o700)
    name = "st-paper-" + hashlib.sha256(candidate).hexdigest()[:20] + ".zip"
    path = directory / name
    if path.exists():
        require(path.read_bytes() == candidate, "CANDIDATE_FILENAME_COLLISION")
    else:
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(candidate)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
    os.chmod(path, 0o600)
    return {
        "status": "LOCAL_ST_PAPER_REVIEW_PACKAGE_PREPARED_NO_DEPLOY",
        "private_local_zip": str(path),
        "archive_proof": proof,
        "cloudformation_control_plane": control,
        "deployment_authorized": False,
        "deployment_method": "REVIEW_CLOUDFORMATION_AND_RUNTIME_SCHEDULE_DRIFT_FIRST",
        "notes": [
            "DO NOT SHARE OR PUSH THE ZIP; it contains the original private handler.",
            "DO NOT run lambda update-function-code or a CFN update from this preview.",
            "No 2026-11-05 Paper receipt, continuity marker or NAV is fabricated.",
            "Requires review of ST-only immutable artifact, CFN change set and post-deployment evidence.",
        ],
        "aws_mutations": False,
        "paper_backfill": False,
        "prod_changes": False,
        "broker_orders": False,
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prepare", action="store_true",
                   help="Create private local review ZIP (no AWS writes)")
    a = p.parse_args()
    require(a.prepare, "RUN_WITH_--prepare_FOR_LOCAL_ST_ONLY_PREVIEW")
    import boto3
    sdk = boto3.session.Session(region_name=REGION)
    clients = {n: sdk.client(n) for n in
               ("sts", "cloudformation", "events", "lambda", "s3")}
    with urlopen(FIXED_SOURCE_URL, timeout=35) as source:
        fixed = read_limited(source, MODULE_SIZE_LIMIT)
    result = prepare_local_review_artifact(clients, fixed, Path.home())
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED_NO_DEPLOY", "reason": str(exc)[:280],
                          "aws_mutations": False, "prod_changes": False,
                          "broker_orders": False, "paper_backfill": False}))
        raise SystemExit(2)

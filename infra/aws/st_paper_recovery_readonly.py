#!/usr/bin/env python3
"""Read-only StockLens ST deployment and missing-Paper-evidence attestation.

Never deploys code, acknowledges alerts, invokes Lambda, writes to S3,
recreates lost receipts, or prints signed Lambda download URLs or source code.
The deployed ZIP is analyzed only in memory for package provenance.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
from datetime import date
from urllib.request import urlopen
from zipfile import ZipFile, BadZipFile

ACCOUNT = "634740393398"
REGION = "eu-central-1"
ST_STACK = "stocklens-st"
PROD_STACK = "stocklens-prod"
ST_BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
PROD_BUCKET = "stocklens-prod-candidatedata-c3yge4ymwb7u"
BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK"
VERIFIED_PUBLIC_PAPER_GIT_BLOB = "ea8427b32899f713468f072dee80ee71216289bf"
ZIP_LIMIT = 100_000_000


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def git_blob_sha(content: bytes) -> str:
    return hashlib.sha1(b"blob " + str(len(content)).encode() + b"\\0" + content).hexdigest()


def inspect_archive(payload: bytes, expected_code_sha: str) -> dict:
    """Inspect bytes, never extract or execute Lambda source."""
    actual_sha = base64.b64encode(hashlib.sha256(payload).digest()).decode()
    require(actual_sha == expected_code_sha, "DEPLOYED_ZIP_SHA256_MISMATCH")
    try:
        with ZipFile(io.BytesIO(payload)) as z:
            names = set(z.namelist())
            independent = "infra/aws/independent_paper.py"
            paper_module = "stocklens/paper.py"
            require(len(names) == len(z.namelist()), "DUPLICATE_DEPLOYED_ZIP_MEMBERS")
            outcome = {
                "zip_sha256_matches_lambda": True,
                "paper_entrypoint_in_zip": independent in names,
                "paper_engine_in_zip": paper_module in names,
                "paper_engine_git_blob": None,
                "engine_matches_verified_github_fix": False,
                "entrypoint_git_blob": None,
            }
            if paper_module in names:
                raw = z.read(paper_module)
                blob_sha = git_blob_sha(raw)
                outcome["paper_engine_git_blob"] = blob_sha
                outcome["engine_matches_verified_github_fix"] = (
                    blob_sha == VERIFIED_PUBLIC_PAPER_GIT_BLOB
                )
            if independent in names:
                outcome["entrypoint_git_blob"] = git_blob_sha(z.read(independent))
            return outcome
    except (BadZipFile, OSError, KeyError, ValueError) as exc:
        raise RuntimeError("DEPLOYED_ZIP_NOT_VERIFIABLE:" + type(exc).__name__) from exc


def stack_outputs(cf, name: str) -> dict:
    stacks = cf.describe_stacks(StackName=name).get("Stacks", [])
    require(len(stacks) == 1 and stacks[0].get("StackStatus") in
            ("CREATE_COMPLETE", "UPDATE_COMPLETE"), "UNSTABLE_STACK:" + name)
    return {x["OutputKey"]: x["OutputValue"] for x in stacks[0].get("Outputs", [])}


def s3_head(s3, bucket: str, key: str) -> dict:
    try:
        result = s3.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        code = (getattr(exc, "response", {}) or {}).get("Error", {}).get("Code", "")
        if str(code) in ("404", "NoSuchKey", "NotFound"):
            return {"status": "NOT_FOUND"}
        return {"status": "READ_UNVERIFIED", "reason": "HEAD_ERROR:" + str(code or type(exc).__name__)}
    version = result.get("VersionId")
    return {
        "status": "VERSIONED_PRESENT" if version and version != "null" else "UNVERSIONED_UNVERIFIED",
        "size_bytes": result.get("ContentLength"),
        "version_id_present": bool(version and version != "null"),
    }


def read_package(fn, opener=urlopen) -> dict:
    result = fn.get_function(FunctionName=ST_STACK + "-paper-candidate")
    cfg = result.get("Configuration", {})
    require(cfg.get("FunctionName") == ST_STACK + "-paper-candidate", "WRONG_PAPER_FUNCTION")
    require(cfg.get("State") == "Active" and cfg.get("LastUpdateStatus") == "Successful",
            "PAPER_LAMBDA_NOT_ACTIVE")
    sha = cfg.get("CodeSha256")
    require(isinstance(sha, str) and len(sha) > 20, "LAMBDA_CODE_SHA_MISSING")
    # The signed URL is sensitive: use it in memory and never print it.
    location = result.get("Code", {}).get("Location")
    require(isinstance(location, str) and location.startswith("https://"),
            "SIGNED_CODE_URL_UNAVAILABLE")
    with opener(location, timeout=35) as response:
        zip_bytes = response.read(ZIP_LIMIT + 1)
    require(len(zip_bytes) <= ZIP_LIMIT, "LAMBDA_ZIP_OVERSIZE")
    return inspect_archive(zip_bytes, sha)


def audit(clients, session: str, *, package_reader=read_package) -> dict:
    require(date.fromisoformat(session).isoformat() == session, "INVALID_ISO_SESSION")
    require(clients["sts"].get_caller_identity().get("Account") == ACCOUNT,
            "WRONG_AWS_ACCOUNT")
    cf, ev = clients["cloudformation"], clients["events"]
    st, prod = stack_outputs(cf, ST_STACK), stack_outputs(cf, PROD_STACK)
    require(st.get("CandidateDataBucket") == ST_BUCKET and
            prod.get("CandidateDataBucket") == PROD_BUCKET, "ST_PROD_BUCKET_NOT_ISOLATED")
    require(clients["s3"].get_bucket_versioning(Bucket=ST_BUCKET).get("Status") == "Enabled",
            "ST_BUCKET_VERSIONING_NOT_ENABLED")
    require(st.get("CandidatePaperFunctionName") == ST_STACK + "-paper-candidate",
            "PAPER_LAMBDA_OUTPUT_MISMATCH")
    rules = {}
    expected_st = {"CandidateSignalOnlyRuleName": "ENABLED",
                   "CandidatePaperOnlyRuleName": "ENABLED",
                   "CandidateOrchestratorRuleName": "DISABLED"}
    for env, outputs, expected in (("ST", st, expected_st),
                                   ("PROD", prod, {x: "DISABLED" for x in expected_st})):
        for logical, required in expected.items():
            actual = ev.describe_rule(Name=outputs[logical]).get("State")
            rules[env + ":" + logical] = actual
            require(actual == required, "UNSAFE_OR_UNEXPECTED_SCHEDULE:" + env + ":" + logical)
    names = {
        "paper_session": "paper/sessions/" + session + ".json",
        "paper_continuity": "paper/continuity/" + session + ".json",
        "signal": "signals/" + session + ".json",
        "paper_genesis": "paper/book/" + BOOK + "/genesis.json",
    }
    candidates = {name: {"key": key, **s3_head(clients["s3"], ST_BUCKET, key)}
                  for name, key in names.items()}
    try:
        pkg = package_reader(clients["lambda"])
    except Exception as exc:
        pkg = {"status": "CODE_PROVENANCE_UNVERIFIED", "reason": str(exc)[:160]}
    missing = [name for name in ("paper_session", "paper_continuity")
               if candidates[name]["status"] != "VERSIONED_PRESENT"]
    return {
        "kind": "STOCKLENS_ST_PAPER_RECOVERY_READ_ONLY",
        "session": session,
        "account_verified": True,
        "st_rules": {x: rules["ST:" + x] for x in expected_st},
        "prod_schedules_all_disabled": all(
            v == "DISABLED" for k, v in rules.items() if k.startswith("PROD:")
        ),
        "versioned_candidate_receipts": candidates,
        "missing_or_unverified_receipts": missing,
        "deployed_paper_package": pkg,
        "qualified_paper_session": False if missing else "NOT_PROVEN_BY_HEAD_ONLY",
        "source_control_gap": "infra/aws/independent_paper.py not present in linked GitHub main",
        "next_action": "VERIFY_SOURCE_ARTIFACT_AND_MISSING_CONTINUITY_BEFORE_ANY_ST_DEPLOY",
        "aws_mutations": False,
        "lambda_invocations": False,
        "broker_orders": False,
        "paper_backfill": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default="2026-11-05")
    args = parser.parse_args()
    try:
        import boto3
        sdk = boto3.session.Session(region_name=REGION)
        report = audit({n: sdk.client(n) for n in
                        ("sts", "cloudformation", "events", "s3", "lambda")},
                       args.session)
        print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
        # Head-only checks can never prove complete Paper execution/reconciliation.
        return 0
    except Exception as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)[:260],
                          "aws_mutations": False, "broker_orders": False}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

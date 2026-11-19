#!/usr/bin/env python3
"""ST-only private Paper Lambda handler *structure* inventory, never execute it.

This is a read-only diagnostic for designing truthful forced BUY/SELL,
Continuity and S3 fault-injection tests against the actual deployed handler.
It intentionally exposes no private source, literal arbitrary strings,
source lines, env values or AWS credentials.

AWS: sts:GetCallerIdentity + lambda:GetFunction ONLY. Lambda not invoked.
No S3 PUT, no EventBridge, no broker orders, no PROD mutation.
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import sys
import zipfile

from infra.aws import sl63_deployed_paper_source_parity as zip_check

SOURCE = "infra/aws/independent_paper.py"
# Only print these predeclared public/documented mode markers, never emit
# unexpected private literal values verbatim.
DOCUMENTED_MODES = (
    "STAGING_PAPER_ONLY",
    "STAGING_PAPER_BOOTSTRAP_PREFLIGHT",
    "STAGING_PAPER_SCHEDULE_READINESS",
    "STAGING_PAPER_SIMULATE",
    "STAGING_PAPER_INJECT",
    "STAGING_PAPER_DRY_RUN",
    "STAGING_PAPER_FAULT_INJECTION",
    "STAGING_PAPER_TEST",
)
SAFE_STATUS_PREFIXES = ("STAGING_", "STAGED_", "HALTED", "FAIL_CLOSED")
AUDITED_METHODS = (
    "put_object", "get_object", "head_object", "list_object_versions",
    "copy_object", "delete_object", "put_item", "update_item",
    "transact_write_items", "invoke", "publish", "get_function",
    "get_function_configuration", "put_events", "describe_rule",
)
# Do not claim that a static AST finding is a runtime behavioral test.
WRITE_METHODS = frozenset((
    "put_object", "copy_object", "delete_object", "put_item",
    "update_item", "transact_write_items", "publish", "put_events",
))
INVENTORY_SCHEMA = "sl63-private-deployed-paper-handler-ast-topology-v1"


def require(cond, msg):
    if not cond:
        raise RuntimeError(msg)


def analyze_private_source(raw: bytes):
    require(0 < len(raw) < 1_000_000, "PRIVATE_HANDLER_UNEXPECTED_SIZE")
    # No import or eval: only parse syntax tree of local Lambda ZIP bytes.
    tree = ast.parse(raw, filename="<private_handler_not_disclosed>")
    defs = [n for n in tree.body if isinstance(n, (
        ast.FunctionDef, ast.AsyncFunctionDef))]
    exports = {n.name for n in defs}
    safe_functions = {
        "handler": "handler" in exports,
        "preflight_handler": "preflight_handler" in exports,
    }
    require(safe_functions["handler"], "PRIVATE_HANDLER_ENTRYPOINT_NOT_DEFINED")
    literals = {n.value for n in ast.walk(tree)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)}
    modes = {m: m in literals for m in DOCUMENTED_MODES}
    calls = {name: 0 for name in AUDITED_METHODS}
    call_nodes = []
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call):
            continue
        f = n.func
        if isinstance(f, ast.Attribute) and f.attr in calls:
            calls[f.attr] += 1
            call_nodes.append((f.attr, n.lineno))
        elif isinstance(f, ast.Name) and f.id in calls:
            calls[f.id] += 1
            call_nodes.append((f.id, n.lineno))
    # Count imported module families only. Do not reveal internal module names
    # or private implementation details.
    imports = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imports.extend(x.name for x in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module:
            imports.append(n.module)
    families = {
        "stocklens": any(x == "stocklens" or x.startswith("stocklens.") for x in imports),
        "boto3": any(x == "boto3" or x.startswith("boto3.") for x in imports),
        "botocore": any(x == "botocore" or x.startswith("botocore.") for x in imports),
    }
    # Modes in body versus nested preflight functions: structural only, does
    # not attest actual response behavior or guarantee branch reachability.
    branches = sum(
        1 for n in ast.walk(tree)
        if isinstance(n, (ast.If, ast.Match, ast.IfExp))
    )
    return {
        "schema": INVENTORY_SCHEMA,
        "private_handler_sha256": hashlib.sha256(raw).hexdigest(),
        "private_handler_present": True,
        "handler_entrypoints": safe_functions,
        "top_level_function_count": len(defs),
        "conditional_branch_count": branches,
        "documented_mode_literal_presence": modes,
        "sdk_method_name_occurrences_in_ast": calls,
        "potential_write_operation_names_present": sorted(
            name for name in WRITE_METHODS if calls[name] > 0
        ),
        "import_family_presence": families,
        "source_disclosed": False,
        "private_handler_imported_or_executed": False,
        "private_handler_s3_paths_observed": False,
        "runtime_broker_safety_verified": False,
        "actual_handler_end_to_end_tested": False,
        "static_only_not_execution_proof": True,
    }


def source_from_verified_zip(data: bytes):
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        names=z.namelist()
        require(len(names) == len(set(names)), "DUPLICATE_LAMBDA_ZIP_ENTRIES")
        require(SOURCE in names, "PRIVATE_PAPER_HANDLER_MISSING_FROM_DEPLOYED_ZIP")
        require(z.getinfo(SOURCE).file_size <= 1_000_000,
                "PRIVATE_SOURCE_OVERSIZED_NO_READ")
        return z.read(SOURCE)


def inspect_only():
    import boto3
    sdk=boto3.session.Session(region_name=zip_check.REGION)
    data,cfg=zip_check.authenticated_download(sdk.client("sts"),sdk.client("lambda"))
    _,handler=zip_check.inspect_zip(data, __import__("pathlib").Path("."))
    require(handler["module_bundled"], "PRIVATE_HANDLER_NOT_BUNDLED")
    src=source_from_verified_zip(data)
    analysis=analyze_private_source(src)
    require(analysis["private_handler_sha256"]==handler["module_sha256"],
            "PRIVATE_SOURCE_SHA_MISMATCH")
    return {
        "status":"DEPLOYED_PRIVATE_HANDLER_STATIC_TOPOLOGY_OBSERVED_NOT_TESTED",
        "lambda_function_name":zip_check.NAME,
        "lambda_code_sha256_b64":cfg["CodeSha256"],
        "exact_aws_zip_hash_authenticated":True,
        "aws_mutations":False,
        "lambda_invocations":False,
        "s3_writes":False,
        "broker_orders":False,
        "prod_changes":False,
        "topology":analysis,
        "next_required":"isolated_exact-private-handler_E2E_forced-BUY-SELL-and-S3-continuity",
    }


def main():
    try:
        out=inspect_only()
        code=0
    except Exception as exc:
        out={"status":"PRIVATE_HANDLER_TOPOLOGY_UNVERIFIED_BLOCKED",
             "reason":str(exc)[:230],
             "error_type":type(exc).__name__,
             "aws_mutations":False,
             "lambda_invocations":False,
             "broker_orders":False}
        code=2
    print(json.dumps(out,indent=2,sort_keys=True))
    return code


if __name__ == "__main__":
    sys.exit(main())

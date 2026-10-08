"""Fail closed on incomplete public source handoffs, before the heavy research batch."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

MANIFEST = Path("ci_transfer_manifest.json")
# Generated output and the one-shot trigger are not source-code inputs.
DYNAMIC_PREFIXES = ("docs/", "shadow_history/", "historical_replay/", "research/prospective/", "research/data/")
EXCLUDED = {"ci_transfer_manifest.json", ".github/workflows/shadow-trigger.txt"}
MANDATORY = (
    "requirements.txt",
    ".github/workflows/shadow.yml",
    "research/prospective/registry.json",
    "governance/qc_724_daily_state_manifest.json",
    "governance/qc_724_order_golden_master.json",
    "research/golden_evidence/qc_68920881.json",
)
LOCAL_PREFIXES = (
    "stocklens", "research_", "prospective_", "dashboard_", "benchmark_", "backtest_",
    "qc_", "lean_", "parity_", "baseline_", "data_", "risk_", "transition_",
    "artifact_", "workbench_", "publication_", "paper_", "hybrid_", "experiment_",
    "execution_", "market_", "source_", "forward_", "yahoo_", "golden_", "signal_",
    "simulator_", "broker_", "recovery_", "trade_", "level_", "context_", "health_",
    "incident_", "slo_", "cost_", "vol_", "pulse_", "drawdown_", "tqqq_",
    "frozen8_", "decade_", "state_", "robustness_", "change_", "daily_", "evidence_",
    "decision_", "order_", "long_", "user_", "pipeline_", "shock_", "slow_",
    "asymmetric_", "orthogonal_", "sparse_", "parameter_", "leveraged_",
)


def in_scope(path: str) -> bool:
    return path not in EXCLUDED and not path.startswith(DYNAMIC_PREFIXES)


def tracked_paths() -> set[str]:
    result = subprocess.check_output(["git", "ls-files", "-z"])
    return {path.decode() for path in result.split(bytes([0])) if path}


def git_blob_sha(path: str) -> str:
    return subprocess.check_output(["git", "hash-object", "--", path], text=True).strip()


def import_roots(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def verify() -> dict:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1 or manifest.get("kind") != "STOCKLENS_COMPLETE_SOURCE_HANDOFF":
        raise ValueError("invalid handoff manifest")
    expected = manifest.get("files")
    if not isinstance(expected, dict) or not expected:
        raise ValueError("empty or invalid handoff manifest")
    tracked = tracked_paths()
    current = {path for path in tracked if in_scope(path)}
    missing = sorted(set(expected) - current)
    extra = sorted(current - set(expected))
    modified = sorted(path for path in expected if path in current and git_blob_sha(path) != expected[path])
    mandatory_missing = sorted(path for path in MANDATORY if not Path(path).is_file())
    source_paths = sorted(path for path in tracked if path.endswith(".py") and Path(path).is_file())
    local_missing = {}
    syntax_errors = {}
    for path in source_paths:
        try:
            roots = import_roots(ast.parse(Path(path).read_text(encoding="utf-8"), filename=path))
        except SyntaxError as exc:
            syntax_errors[path] = f"{exc.lineno}: {exc.msg}"
            continue
        unresolved = sorted(root for root in roots if root.startswith(LOCAL_PREFIXES)
                            and not Path(root + ".py").is_file()
                            and not Path(root, "__init__.py").is_file())
        if unresolved:
            local_missing[path] = unresolved
    result = {
        "status": "PASS" if not (missing or extra or modified or mandatory_missing or local_missing or syntax_errors) else "FAIL",
        "locked_source_files": len(expected),
        "python_files": len(source_paths),
        "missing_locked_files": missing,
        "unexpected_locked_files": extra,
        "modified_locked_files": modified,
        "mandatory_missing": mandatory_missing,
        "unresolved_project_imports": local_missing,
        "syntax_errors": syntax_errors,
        "signal_mutated": False,
        "model_promotion_allowed": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    if result["status"] != "PASS":
        raise SystemExit(2)
    return result


if __name__ == "__main__":
    verify()

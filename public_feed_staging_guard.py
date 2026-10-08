"""Fail closed when dashboard feeds are generated but not staged for publication."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

CORE_WORKBENCH = {
    "workbench.json", "workbench_evidence_manifest.json",
    "workbench_selfcheck.json", "workbench_evidence_bundle.json",
    "workbench_evidence_health.json", "research_curves.json",
    "simulator_smoke.json",
}

def validate():
    html = Path("docs/index.html").read_text(encoding="utf-8")
    index_feeds = set(re.findall(r"(?:getJSON|fetch)\s*\(\s*['\"]([^'\"]+\.json)", html))
    if not index_feeds:
        raise SystemExit("DASHBOARD_FEED_GUARD_INVALID_EMPTY_INDEX")
    required = {"docs/" + name.removeprefix("./") for name in index_feeds}
    required.update("docs/" + feed for feed in CORE_WORKBENCH)
    staged = set(subprocess.check_output(["git", "ls-files", "-z"]).decode().split(chr(0)))
    missing = sorted(p for p in required if not Path(p).is_file())
    not_staged = sorted(p for p in required if p not in staged)
    mismatched = []
    for p in required - set(missing) - set(not_staged):
        index_sha = subprocess.check_output(["git", "rev-parse", ":" + p], text=True).strip()
        worktree_sha = subprocess.check_output(["git", "hash-object", "--", p], text=True).strip()
        if index_sha != worktree_sha:
            mismatched.append(p)
    if missing or not_staged or mismatched:
        raise SystemExit("DASHBOARD_FEEDS_NOT_PUBLISHED " + repr({
            "missing": missing, "not_staged": not_staged,
            "unstaged_changes": sorted(mismatched),
        }))
    print(f"DASHBOARD_FEEDS_STAGED_OK: {len(required)} required feeds")

if __name__ == "__main__":
    validate()

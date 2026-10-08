"""Publish source-grounded, fail-closed public dashboard feeds for the current run."""
from __future__ import annotations
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def read(path, default=None):
    p = Path(path)
    if not p.is_file():
        return default
    return json.loads(p.read_text(encoding="utf-8"))


def save(name, value):
    p = Path("docs") / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def build():
    queue = read("research/queue.json", {"experiments": []})
    state = read("research/AUTONOMY_STATE.json", {})
    registry = read("research/prospective/registry.json", {"candidates": [], "last_ingestion_audit": []})
    dossiers = read("research/validation/challenger_dossiers.json", {"dossiers": []})
    health = read("docs/workbench_evidence_health.json", {})
    data = read("docs/data.json", {})
    capital = read("docs/capital_readiness.json", {})
    smoke = read("docs/simulator_smoke.json", {})
    publication = read("shadow_history/publication_gate.json", {})
    now = datetime.now(timezone.utc).isoformat()
    experiments = queue.get("experiments", [])
    candidates = registry.get("candidates", [])
    dispositions = {x.get("experiment_id"): x for x in dossiers.get("dossiers", [])}
    prospective = {x.get("experiment_id"): x for x in candidates}
    audits = {x.get("experiment_id"): x for x in registry.get("last_ingestion_audit", [])}
    snapshots = []
    for x in experiments:
        eid = x["experiment_id"]
        pro = prospective.get(eid)
        audit = audits.get(eid, {})
        validated = bool(pro and audit.get("source_status") == "AVAILABLE" and audit.get("definition_matches_registration") is True and audit.get("persisted_prospective_rows") is not None)
        snapshots.append({
            "id": eid, "name": x.get("name", eid), "hypothesis": x.get("hypothesis", ""),
            "effective_status": x.get("status", "UNKNOWN"),
            "queue_status": x.get("status", "UNKNOWN"),
            "disposition": dispositions.get(eid, {}).get("disposition", "UNVERIFIED"),
            "robustness": dispositions.get(eid, {}).get("robustness", "NOT_VALIDATED"),
            "reason": x.get("blocked_reason") or ("Prospective source is unverified" if pro and not validated else "Research evidence is not authorization for promotion"),
            "prospective": {"inception_date": pro.get("inception_date"), "sessions": int(audit["persisted_prospective_rows"]), "status": pro.get("status")} if validated else None
        })
    save("research_snapshot.json", {
        "schema_version": 1, "source_git_sha": os.getenv("GITHUB_SHA"),
        "milestone": state.get("current_milestone", "UNVERIFIED"),
        "experiments": snapshots, "next_actions": state.get("next_work", []),
        "automatic_promotion": False, "warning": "Evidence and prospective data are not trading authorization."
    })
    cards = [{"experiment_id": x["id"], "state": "BLOCKED_REVIEW" if x["effective_status"] == "BLOCKED" else "RESEARCH_ONLY",
              "reason": x["reason"] + " Independent-clone audit unavailable in public CI.",
              "near_clones": []} for x in snapshots]
    save("opportunity_board.json", {
        "schema_version": 1, "cards": cards,
        "next_challenger_gate": {"status": "NO_NEW_CHALLENGER_AUTHORIZED",
         "requirements": ["independent evidence", "predeclaration", "point-in-time data", "out-of-sample validation"]},
        "automatic_promotion": False
    })
    save("hypothesis_backlog.json", {"schema_version": 1, "ideas": [], "status": "NO_NEW_IDEA_AUTHORIZED", "baseline": "StockLens 8.0 FROZEN"})
    checks = [{"idea_id": "PIT-BREADTH", "status": "BLOCKED", "evidence": ["No verified point-in-time constituent history"],
               "required_next": "Qualify survivorship-safe historical data before research."}]
    save("discovery_data_readiness.json", {"schema_version": 1, "status": "NO_NEW_DATA_READY", "checks": checks,
         "policy": "Research data must be independently qualified before new hypotheses can be tested.", "ready_ideas": []})
    save("data_source_registry.json", {"schema_version": 1, "sources": [
        {"source_id": "QQQ-DAILY", "status": "EXISTING_BASELINE_DATA", "purpose": "QQQ-only baseline evidence", "allowed_for_new_hypothesis": False},
        {"source_id": "PIT-BREADTH", "status": "MISSING", "purpose": "Survivorship-safe breadth", "allowed_for_new_hypothesis": False, "acquisition_requirement": "Point-in-time data"}
    ], "qualified_new_hypothesis_sources": []})
    save("data_acquisition_status.json", {"schema_version": 1, "status": "NO_NEW_SOURCE_QUALIFIED", "results": [],
        "qualified_sources": [], "automatic_experiment_authorization": False})
    stages = {"discovery_ideas": 0, "blocked_data_ideas": len(checks), "data_ready_ideas": 0,
              "experiments_total": len(experiments), "prospective_candidates": len(candidates)}
    save("pipeline_summary.json", {"schema_version": 1, "stages": stages,
        "prospective": [{"experiment_id": c["experiment_id"], "inception_date": c.get("inception_date"),
            "sessions": int(audits.get(c["experiment_id"], {}).get("persisted_prospective_rows") or 0),
            "status": c.get("status")} for c in candidates],
        "next_gate": "QUALIFIED_DATA_AND_PREDECLARATION", "new_experiment_authorized": False})
    try:
        raw = subprocess.check_output(["git", "log", "-12", "--pretty=format:%H%x1f%aI%x1f%s"], text=True)
        activity = []
        for line in raw.splitlines():
            sha, date, title = line.split("\x1f", 2)
            activity.append({"short_sha": sha[:7], "date": date, "title": title,
                "kind": "FIX" if title.startswith(("ci:", "fix:")) else "PROJECT", "impact": "Repository change; CI validation is separate."})
    except (subprocess.CalledProcessError, ValueError):
        activity = []
    save("activity.json", {"schema_version": 1, "items": activity,
        "high_signal_items": activity, "recent_summary": activity[:3]})
    freshness = health.get("market_session_freshness", "UNKNOWN")
    pub_ok = publication.get("status") == "ALLOW"
    items = [{"area": "Market data", "status": freshness, "summary": "Completed-session signal freshness", "attention": freshness != "CURRENT"},
             {"area": "Publication", "status": "PASS" if pub_ok else "BLOCKED",
              "summary": "Current generation requires a validated publication gate", "attention": not pub_ok},
             {"area": "Claim Ledger", "status": "BLOCKED", "summary": "Canonical claim ledger absent unless independently verified",
              "attention": True, "blockers": ["CANONICAL_CLAIM_LEDGER_NOT_VERIFIED"], "observational_gaps": ["Full LEAN input parity is not proven."]}]
    save("project_status.json", {"schema_version": 1, "overall_status": "REVIEW_REQUIRED", "items": items,
        "automatic_trading_authorized": False, "generated_at_utc": now})
    save("daily_brief.json", {"schema_version": 1, "summary": "Research-only. Canonical publication claims require independent verification.",
        "research": {"milestone": state.get("current_milestone", "UNVERIFIED"), "next_action": (state.get("next_work") or ["Review evidence"])[0]},
        "simulator": {"status": smoke.get("accounting_invariants", {}).get("status", "UNKNOWN"),
                      "sessions": smoke.get("sessions", 0)},
        "blockers": [{"area": x["area"], "status": x["status"]} for x in items if x["attention"]],
        "source_git_sha": os.getenv("GITHUB_SHA")})
    expected = ["data.json", "workbench.json", "research_snapshot.json", "activity.json",
       "daily_brief.json", "project_status.json", "execution_observation.json", "capital_readiness.json",
       "simulator_smoke.json", "research_curves.json", "pipeline_summary.json", "opportunity_board.json"]
    missing = [f for f in expected if not (Path("docs") / f).is_file()]
    save("site_health.json", {"schema_version": 1, "git_sha": os.getenv("GITHUB_SHA"),
        "built_at_utc": now, "healthy": bool(not missing and pub_ok and freshness == "CURRENT"),
        "artifact_freshness": {"status": freshness}, "missing_feeds": missing,
        "warning": "Healthy means these feeds exist and freshness/publication gates pass; not LEAN execution parity."})
    return {"status": "PASS" if not missing else "BLOCKED_MISSING_FEEDS", "missing_feeds": missing,
            "candidates": len(candidates), "automatic_trading_authorized": False}


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))

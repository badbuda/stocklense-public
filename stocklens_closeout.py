"""StockLens operational closeout evidence: fail closed, never invent AWS or Paper.

Rebuild from current PUBLIC artifacts after a Shadow publication. This does not
call AWS or brokers, run a backtest, or substitute GitHub artifacts for receipts.
"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import hashlib
import json
from pathlib import Path

SOURCE = {
    "signals": "docs/portal-history.json",
    "paper": "docs/paper_portfolio_integrity.json",
    "forward": "docs/paper_forward_audit.json",
    "readiness": "docs/backtest_live_readiness.json",
    "combinations": "docs/st-combo-results.json",
}
JSON_OUT = Path("docs/stocklens-closeout.json")
MD_OUT = Path("docs/stocklens-closeout.md")


def _day(value, name):
    if not isinstance(value, str):
        raise ValueError("MISSING_DATE:" + name)
    try:
        d = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("INVALID_DATE:" + name) from exc
    if d.isoformat() != value:
        raise ValueError("NON_CANONICAL_DATE:" + name)
    return d


def load(repo=Path(".")):
    docs, fingerprints = {}, {}
    for name, file in SOURCE.items():
        p = repo / file
        raw = p.read_bytes()  # no missing source may be silently inferred
        docs[name] = json.loads(raw)
        fingerprints[name] = hashlib.sha256(raw).hexdigest()
    return docs, fingerprints


def evaluate(docs, fingerprints):
    s, p, f, r, c = (docs[k] for k in SOURCE)
    sd = _day(s.get("updated_session"), "SIGNAL")
    pd = _day(p.get("latest_session"), "PAPER")
    fd = _day(f.get("current_signal_date"), "FORWARD_SIGNAL")
    prior = _day(f.get("persisted_signal_date"), "PERSISTED_SIGNAL")
    end = _day(c.get("period", {}).get("end"), "RESEARCH_END")

    if (s.get("observed_ohlc_available") is not True or
        s.get("instruments") != ["QQQ", "TQQQ"] or
        s.get("live_trading_authorized") is not False):
        raise ValueError("INVALID_FROZEN_SIGNAL_SOURCE")
    if fd != sd or prior > fd:
        raise ValueError("FORWARD_SIGNAL_SOURCE_INCONSISTENT")
    if pd > sd:
        raise ValueError("PAPER_FUTURE_DATED")
    if (p.get("broker_fills_observed") is not False or
        p.get("live_trading_authorized") is not False):
        raise ValueError("FALSE_BROKER_EXECUTION_CLAIM")
    if (f.get("live_trading_authorized") is not False or
        f.get("backfill_authorized") is not False):
        raise ValueError("UNAUTHORIZED_BACKFILL_OR_LIVE")
    if (r.get("kind") != "STOCKLENS_LIVE_READINESS" or
        r.get("automated_live_trading_authorized") is not False or
        r.get("automatic_model_promotion") is not False or
        r.get("capital_scaling_authorized") is not False):
        raise ValueError("UNVERIFIED_CAPITAL_AUTHORIZATION")
    checks = r.get("checks")
    if not isinstance(checks, list) or len(checks) < 10:
        raise ValueError("READINESS_CHECKLIST_ABSENT")
    statuses = [z.get("status") for z in checks]
    if any(v not in ("PASS", "BLOCKED") for v in statuses):
        raise ValueError("UNKNOWN_READINESS_GATE")
    passed, blocked = statuses.count("PASS"), statuses.count("BLOCKED")
    if passed != r.get("passed_count") or blocked != r.get("blocked_count"):
        raise ValueError("READINESS_COUNTS_DO_NOT_RECONCILE")
    ids = [z.get("id") for z in checks]
    if len(set(ids)) != len(ids):
        raise ValueError("DUPLICATE_READINESS_GATES")
    failed_ids = {z["id"] for z in checks if z["status"] == "BLOCKED"}
    if set(r.get("blockers", [])) != failed_ids:
        raise ValueError("READINESS_BLOCKER_DETAILS_DO_NOT_RECONCILE")
    if (c.get("kind") != "SL9_031_ST_REAL_ETF_OVERLAY_COMBINATIONS" or
        c.get("frozen_daily_parity_all_stress_cases") is not True or
        c.get("actual_etf_observations_no_synthetic_prices") is not True or
        c.get("automatic_promotion") is not False or
        c.get("broker_actions") is not False or
        c.get("aws_st_paper_runs") is not False or
        c.get("pristine_out_of_sample") is not False or
        c.get("source_independently_audited") is not False or
        c.get("case_count") != 56 or
        c.get("stress_runs") != 224 or
        len(c.get("results", [])) != 56):
        raise ValueError("RESEARCH_CANNOT_BE_PRESENTED_AS_VERIFIED_HISTORICAL")
    if end > sd:
        raise ValueError("RESEARCH_AHEAD_OF_SIGNAL")
    qualified = sum(x.get("continuation_only") is True for x in c["results"])
    if type(f.get("paper_sessions")) is not int or f["paper_sessions"] < 0:
        raise ValueError("INVALID_FORWARD_PAPER_SESSIONS")
    if type(f.get("explicit_missed_sessions")) is not int or f["explicit_missed_sessions"] < 0:
        raise ValueError("INVALID_MISSED_SESSION_COUNT")
    if type(p.get("verified_paper_sessions")) is not int or p["verified_paper_sessions"] < 0:
        raise ValueError("INVALID_PAPER_VERIFICATION")
    if p["verified_paper_sessions"] != f["paper_sessions"]:
        raise ValueError("PAPER_SESSION_COUNTS_DISAGREE")
    if type(r.get("paired_forward_paper_sessions")) is not int:
        raise ValueError("UNKNOWN_PAIRED_FORWARD_COUNT")
    if r["paired_forward_paper_sessions"] > f["paper_sessions"]:
        raise ValueError("PAIRED_FORWARD_GT_PAPER")
    gap = (sd - pd).days
    paper_stale = gap > 0
    # A PASS paper accounting result certifies only the OLD recorded rows.
    if not p.get("status", "").startswith("PASS_MODELLED_PAPER_ACCOUNTING"):
        accounting_status = "BLOCKED"
    else:
        accounting_status = "HISTORICAL_MODELLED_ONLY"
    # User-visible status is computed from evidence; NEVER turn an empty deployed
    # AWS stack into an operational green stack using metadata or a CI flag.
    primary = {
        "frozen_shadow": {
            "status": "SOURCE_PRESENT_NOT_AWS_EXECUTION",
            "observed_signal_asof": sd.isoformat(),
        },
        "historical_combination_research": {
            "status": "HISTORICAL_CI_VERIFIED_NOT_FORWARD",
            "study": "SL9-031",
            "observed_ending_session": end.isoformat(),
            "arm_count": c["case_count"],
            "stress_tests": c["stress_runs"],
            "qualified_for_auto_promotion": 0,
            "continuation_screen_arms": qualified,
        },
        "legacy_paper": {
            "status": "STALE" if paper_stale else "DATE_MATCH_ONLY_NOT_AWS_VERIFIED",
            "last_recorded_session": pd.isoformat(),
            "calendar_days_behind_signal": gap,
            "verified_modelled_sessions": p["verified_paper_sessions"],
            "explicit_missed_execution_sessions": f["explicit_missed_sessions"],
            "independent_broker_fills": False,
            "accounting": accounting_status,
        },
        "prospective_frozen_paper": {
            "status": "BLOCKED_UNPAIRED" if r["paired_forward_paper_sessions"] == 0
                       else "PARTIAL_NEEDS_EXTERNAL_REVIEW",
            "paired_forward_sessions": r["paired_forward_paper_sessions"],
            "forward_sessions_reported": f["paper_sessions"],
            "no_backfill": True,
        },
        "aws_st": {"status": "NOT_VERIFIED_FROM_GITHUB",
                   "note": "No verified ST S3 receipt, current Lambdas/schedules or research runner evidence available here."},
        "aws_prod": {"status": "NOT_VERIFIED_FROM_GITHUB",
                     "note": "Stack existence is NOT a qualified, active prospective Paper book."},
        "readiness": {"status": "BLOCKED_FOR_LIVE_TRADING",
                      "passed": passed, "blocked": blocked, "total": len(checks),
                      "blocked_ids": sorted(failed_ids)},
        "dashboard": {"status": "STATIC_RESEARCH_ONLY_NOT_OPERATIONAL_GREEN",
                      "note": "Browser CDNs passing does not resolve a stale Paper archive."},
    }
    # Strong invariant: don't show overall GREEN even when all dates temporarily
    # match; verified AWS, forward and external source gates are still absent.
    return {
        "schema_version": 1,
        "kind": "STOCKLENS_EVIDENCE_CLOSEOUT",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "overall": "BLOCKED_OPERATIONAL_NOT_RESEARCH",
        "automated_live_trading_authorized": False,
        "automatic_model_promotion": False,
        "broker_orders": False,
        "source_sha256": fingerprints,
        "components": primary,
        "work_items": [
            {"priority": "P0", "id": "PAPER_FORWARD_CHAIN",
             "status": "BLOCKED", "required": "New independent genesis and future-only signal→Paper receipts in ST; never backfill misses."},
            {"priority": "P0", "id": "ST_AWS_READBACK",
             "status": "AWAITING_INDEPENDENT_AWS_READ",
             "required": "Read-only S3 list/head/hash and EventBridge/Lambda checks in exact stocklens-st."},
            {"priority": "P0", "id": "PROD_PAPER_ACCEPTANCE",
             "status": "NOT_AUTHORIZED",
             "required": "No PROD schedule activation before provider parity, safe genesis, receipt/ledger and alerts."},
            {"priority": "P0", "id": "PORTAL_E2E_PAPER_FRESHNESS",
             "status": "BLOCKED" if paper_stale else "AWAITING_FULL_E2E",
             "required": "New legitimate Paper archive must match completed sessions; do not suppress freshness checks."},
            {"priority": "P1", "id": "SECOND_SOURCE_AND_PIT",
             "status": "BLOCKED",
             "required": "Independent vendor, corporate action and price-first-seen evidence."},
            {"priority": "P1", "id": "LEAN_AND_EXECUTION_PROOF",
             "status": "BLOCKED",
             "required": "Same-run LEAN fills/equity plus minute executable quote provenance."},
            {"priority": "P1", "id": "FORWARD_OOS_ETF_MIXES",
             "status": "NOT_STARTED_CERTIFIED",
             "required": "Register cohort before future sessions and compare lag-1 frozen vs fixed mixes with prospectively captured inputs."},
            {"priority": "P2", "id": "BROKER_SANDBOX_AND_RISK_POLICY",
             "status": "BLOCKED",
             "required": "Authorized sandbox, kill switch, funding, spreads and human capital risk acceptance."},
        ],
    }


def markdown(report):
    c = report["components"]
    rows = ["# StockLens — evidence-based closeout", "",
            "Research-only / operationally BLOCKED. Generated " + report["generated_at_utc"] + ".",
            "Never imply broker execution or live AWS proof from GitHub CI.", "",
            "| Component | Current status | Evidence |",
            "|---|---|---|"]
    rows.append("| Shadow frozen | {} | Signal session {} |".format(
        c["frozen_shadow"]["status"], c["frozen_shadow"]["observed_signal_asof"]))
    rows.append("| Historical ETF combinations | {} | {} arms, {} stress runs, to {} |".format(
        c["historical_combination_research"]["status"],
        c["historical_combination_research"]["arm_count"],
        c["historical_combination_research"]["stress_tests"],
        c["historical_combination_research"]["observed_ending_session"]))
    rows.append("| Legacy modeled Paper | {} | Last {}, {} missed explicit, {} modeled sessions |".format(
        c["legacy_paper"]["status"], c["legacy_paper"]["last_recorded_session"],
        c["legacy_paper"]["explicit_missed_execution_sessions"],
        c["legacy_paper"]["verified_modelled_sessions"]))
    rows.append("| AWS ST | {} | Readback unverified |".format(c["aws_st"]["status"]))
    rows.append("| AWS PROD | {} | Not an accepted Paper book |".format(c["aws_prod"]["status"]))
    rows.append("| Trading readiness | {} | {}/{} checks PASS; {} blocked |".format(
        c["readiness"]["status"],c["readiness"]["passed"],c["readiness"]["total"],c["readiness"]["blocked"]))
    rows += ["", "## Outstanding gates", ""]
    for x in report["work_items"]:
        rows.append("- **{} {} — {}:** {}".format(x["priority"],x["id"],x["status"],x["required"]))
    rows += ["", "No synthetic data, no retrospective Paper fixes, no automatic model promotion.", ""]
    return "\n".join(rows)


def build(repo=Path(".")):
    docs, hashes = load(repo)
    result = evaluate(docs, hashes)
    (repo / JSON_OUT).write_text(json.dumps(result,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    (repo / MD_OUT).write_text(markdown(result),encoding="utf-8")
    print("STOCKLENS_CLOSEOUT_PUBLISHED=" + json.dumps({
        "overall":result["overall"],
        "paper":result["components"]["legacy_paper"]["status"],
        "paper_asof":result["components"]["legacy_paper"]["last_recorded_session"],
        "signal_asof":result["components"]["frozen_shadow"]["observed_signal_asof"],
        "readiness_blocked":result["components"]["readiness"]["blocked"],
        "aws_verified":False,
        "broker_orders":False}))
    return result


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--repo",type=Path,default=Path("."))
    args=parser.parse_args()
    build(args.repo)

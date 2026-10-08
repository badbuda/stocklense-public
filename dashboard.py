from __future__ import annotations

import csv
import json
from pathlib import Path


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def build_dashboard(
    signal_path: str = "output/latest_signal.json",
    signal_history_path: str = "shadow_history/signals.csv",
    paper_ledger_path: str = "paper_portfolio/ledger.csv",
    revision_audit_path: str = "shadow_history/revision_audit.csv",
    historical_summary_path: str = "historical_replay/summary.json",
    out_path: str = "shadow_history/dashboard.md",
    mobile_data_path: str = "docs/data.json",
) -> str:
    signal = json.loads(Path(signal_path).read_text(encoding="utf-8"))
    sig_rows = _read_rows(Path(signal_history_path))
    paper_rows = _read_rows(Path(paper_ledger_path))
    revision_rows = _read_rows(Path(revision_audit_path))
    historical = json.loads(Path(historical_summary_path).read_text()) if Path(historical_summary_path).exists() else None
    x = signal["latest"]
    f = x["features"]

    paper_block = "Paper portfolio has not executed its first forward session yet."
    if paper_rows:
        p = paper_rows[-1]
        transitions = sum(
            1 for r in sig_rows if r.get("action") and r.get("action") != "NO_CHANGE"
        )
        paper_block = f"""- Last paper session: **{p['session_date']}**
- Equity: **${float(p['equity']):,.2f}**
- Cumulative return: **{float(p['cumulative_return']) * 100:.2f}%**
- Drawdown: **{float(p['drawdown']) * 100:.2f}%**
- QQQ shares: **{p['qqq_shares']}**
- TQQQ shares: **{p['tqqq_shares']}**
- Cash: **${float(p['cash']):,.2f}**
- Cumulative fees: **${float(p['cumulative_fees']):,.2f}**
- Cumulative modeled slippage: **${float(p['cumulative_slippage_cost']):,.2f}**
- Prospective signal rows: **{len(sig_rows)}**
- Exposure-changing signal rows: **{transitions}**
- Paper sessions: **{len(paper_rows)}**"""

    audit_block = f"- Nonmaterial same-session input revisions observed: **{len(revision_rows)}**"
    if revision_rows:
        last = revision_rows[-1]
        audit_block += (
            f"\n- Latest input-drift audit: **{last['asof_date']}** "
            f"({last['disposition']})"
        )

    text = f"""# StockLens 8.0 Prospective Dashboard

## Frozen signal

- As of: **{x['asof_date']}**
- Action: **{signal['action']}**
- Level: **{x['level']}**
- Defense: **{'ON' if x['defense_active'] else 'OFF'}**
- Target leverage: **{x['target_leverage']:.2f}x**
- QQQ target: **{x['qqq_weight'] * 100:.2f}%**
- TQQQ target: **{x['tqqq_weight'] * 100:.2f}%**

## Features

- QQQ adjusted close: **{f['close']:.4f}**
- SMA50: **{f['sma50']:.4f}**
- SMA200: **{f['sma200']:.4f}**
- VOL20: **{f['vol20'] * 100:.2f}%**
- MOM12: **{f['mom12'] * 100:.2f}%**

## Historical replay context — NOT prospective evidence

{("- Sessions: **" + str(historical["sessions"]) + "**\n- Window: **" + str(historical["first_date"]) + " → " + str(historical["last_date"]) + "**\n- State transitions: **" + str(historical["state_transitions"]) + "**\n- Defense sessions: **" + str(historical["defense_sessions"]) + "**\n- Level counts: **" + str(historical["level_counts"]) + "**") if historical else "Historical replay not generated yet."}

## Prospective paper portfolio

{paper_block}

## Data-integrity audit

{audit_block}

## Governance

StockLens 8.0 is frozen. This dashboard is observational only and must not be used to retune 8.0 thresholds, filters, or leverage rules.
"""
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    readiness_path=Path("shadow_history/readiness.json")
    context_path=Path("shadow_history/market_context.json")
    readiness=json.loads(readiness_path.read_text()) if readiness_path.exists() else {"status":"PENDING","checks":{}}
    market_context=json.loads(context_path.read_text()) if context_path.exists() else {"mode":"OBSERVATIONAL_ONLY","affects_frozen_signal":False,"vix":None,"fear_greed":None}
    from risk_context import build_risk_context
    from data_quality_summary import build_data_quality
    risk_context=build_risk_context(signal)
    data_quality=build_data_quality()
    def _optional_json(name,default):
        p=Path(name); return json.loads(p.read_text()) if p.exists() else default
    benchmark=_optional_json("shadow_history/benchmark.json",{"status":"WAITING_FOR_PROSPECTIVE_DATA","benchmark":"QQQ"})
    event_journal=_optional_json("shadow_history/event_journal.json",{})
    regime_analytics=_optional_json("shadow_history/regime_analytics.json",{"status":"NO_DATA"})
    change_digest=_optional_json("shadow_history/change_digest.json",{"status":"NO_DATA","changes":[]})
    daily_digest=_optional_json("shadow_history/daily_digest.json",{})
    slo=_optional_json("shadow_history/slo.json",{})
    from transition_explainer import explain_next_transitions
    transition_explanation=explain_next_transitions(signal)
    evidence_maturity=_optional_json("shadow_history/evidence_maturity.json",{"stage":"BOOTSTRAP","prospective_sessions":0})
    risk_telemetry=_optional_json("shadow_history/risk_telemetry.json",{"status":"WAITING_FOR_PROSPECTIVE_DATA","sessions":0})
    experiment_quality=_optional_json("shadow_history/experiment_quality.json",{"status":"LIMITED"})
    anomalies=_optional_json("shadow_history/anomalies.json",{"status":"MISSING","alerts":[]})
    recovery_plan=_optional_json("shadow_history/recovery_plan.json",{"status":"UNKNOWN","steps":[]})
    data_provenance=_optional_json("shadow_history/data_provenance.json",{"status":"MISSING"})
    forward_path=_optional_json("shadow_history/forward_path.json",{"status":"WAITING_FOR_RETURN_PATH"})
    execution_quality=_optional_json("shadow_history/execution_quality.json",{"status":"WAITING_FOR_PROSPECTIVE_DATA"})
    forward_quality=_optional_json("shadow_history/forward_quality.json",{"status":"NO_DATA"})
    qc_parity_dossier=_optional_json("shadow_history/qc_parity_dossier.json",{"status":"REFERENCE_PARITY_ONLY"})
    execution_plan=_optional_json("shadow_history/execution_plan.json",{"status":"MISSING"})
    trade_receipts=_optional_json("shadow_history/trade_receipts.json",{"status":"WAITING_FOR_TRADES"})
    execution_audit=_optional_json("shadow_history/execution_audit.json",{"status":"MISSING"})
    cost_attribution=_optional_json("shadow_history/cost_attribution.json",{"status":"WAITING_FOR_PROSPECTIVE_DATA"})
    execution_readiness=_optional_json("shadow_history/execution_readiness.json",{"status":"BLOCKED"})
    automation_guard=_optional_json("shadow_history/automation_guard.json",{"status":"BLOCKED","next_action":"STOP_AND_REVIEW"})
    execution_cockpit=_optional_json("shadow_history/execution_cockpit.json",{"status":"MISSING","mode":"PAPER","live_submission_authorized":False,"orders":[]})
    execution_policy=_optional_json("shadow_history/execution_policy.json",{"status":"BLOCKED","next_action":"WAIT_FOR_VALID_COCKPIT","automatic_catchup":False,"live_submission_authorized":False})
    capital_readiness=_optional_json("docs/capital_readiness.json",{"stage":"SHADOW_ONLY","scaled_capital_ready":False,"automatic_trading_authorized":False,"observational_only":True})
    prospective_maturity=_optional_json("docs/prospective_maturity.json",{"status":"BLOCKED","producer_current":False,"experiments":[]})
    incident_state=_optional_json("shadow_history/incident_state.json",{"status":"UNKNOWN"})
    publication_gate=_optional_json("shadow_history/publication_gate.json",{"status":"UNKNOWN"})
    artifact_integrity=_optional_json("shadow_history/artifact_integrity.json",{"status":"PENDING","invalid":[]})
    research_provenance=_optional_json("output/research_provenance.json",{"kind":"RESEARCH_PROVENANCE","publication_generation":None})
    dependency_integrity=_optional_json("shadow_history/dependency_integrity.json",{"status":"UNKNOWN"})
    publication_source_sha=publication_gate.get("source_git_sha")
    provenance_source_sha=research_provenance.get("git_sha")
    publication_authoritative=(
        publication_gate.get("status")=="ALLOW"
        and artifact_integrity.get("status")=="PASS"
        and bool(publication_source_sha)
        and publication_source_sha==provenance_source_sha
    )
    if not publication_authoritative:
        publication_gate={**publication_gate,"status":"STALE_OR_UNVERIFIED","authoritative":False}
    else:
        publication_gate={**publication_gate,"authoritative":True}
    context_quality=_optional_json("shadow_history/context_quality.json",{"status":"DEGRADED","blocking":False})
    context_analytics=_optional_json("shadow_history/context_analytics.json",{"status":"WAITING_FOR_CONTEXT_HISTORY"})
    data_provenance=_optional_json("shadow_history/data_provenance.json",{"status":"MISSING"})
    stress_scenarios=_optional_json("shadow_history/stress_scenarios.json",{})
    exposure=_optional_json("shadow_history/exposure.json",{})
    drawdown_budget=_optional_json("shadow_history/drawdown_budget.json",{})
    performance_path = Path("shadow_history/performance.json")
    health_path = Path("shadow_history/health.json")
    performance = json.loads(performance_path.read_text()) if performance_path.exists() else {"status":"WAITING_FOR_PROSPECTIVE_DATA","sessions":len(paper_rows)}
    health = json.loads(health_path.read_text()) if health_path.exists() else {"status":"PENDING","warnings":[],"problems":[]}
    parity_manifest_path=Path("governance/qc_724_daily_state_manifest.json")
    parity_audit_path=Path("shadow_history/qc_daily_parity.json")
    parity_manifest=json.loads(parity_manifest_path.read_text()) if parity_manifest_path.exists() else {}
    parity_audit=json.loads(parity_audit_path.read_text()) if parity_audit_path.exists() else {}
    latest_paper = paper_rows[-1] if paper_rows else None
    trades = _read_rows(Path(paper_ledger_path).with_name("trades.csv"))
    hist_rows = _read_rows(Path("historical_replay/daily_states.csv"))
    history_tail = [{
        "date": r.get("asof_date"), "level": int(r.get("level",0)),
        "defense": str(r.get("defense_active","")).lower()=="true",
        "leverage": float(r.get("target_leverage",0)), "close": float(r.get("close",0)),
        "vol20": float(r.get("vol20",0)), "mom12": float(r.get("mom12",0)),
    } for r in hist_rows[-90:]]
    signal_tail = [{
        "date": r.get("asof_date"), "action": r.get("action"), "level": int(r.get("level",0)),
        "defense": str(r.get("defense_active","")).lower()=="true",
        "leverage": float(r.get("target_leverage",0)),
    } for r in sig_rows[-20:]]
    why = {
        "close_vs_sma200_pct": (float(f["close"])/float(f["sma200"])-1.0) if f["sma200"] else None,
        "sma50_vs_sma200_pct": (float(f["sma50"])/float(f["sma200"])-1.0) if f["sma200"] else None,
        "vol_to_level3_drop": 0.32-float(f["vol20"]),
        "mom12": float(f["mom12"]),
        "trend_retention_floor": float(f["sma200"])*0.99,
        "trend_reentry_threshold": float(f["sma200"])*1.01,
    }
    mobile = {
        "schema_version": 1,
        "model": "StockLens 8.0",
        "mode": "SHADOW_FROZEN",
        "signal": {
            "asof_date": x["asof_date"], "action": signal["action"], "level": x["level"],
            "defense_active": x["defense_active"], "target_leverage": x["target_leverage"],
            "qqq_weight": x["qqq_weight"], "tqqq_weight": x["tqqq_weight"],
            "cash_weight": max(0.0, 1.0-x["qqq_weight"]-x["tqqq_weight"]),
            "generated_at_utc": signal.get("generated_at_utc"),
            "source": signal.get("source_audit",{}).get("source") or signal.get("source"),
            "features": f,
        },
        "market_prices": {
            "qqq_adjusted_close": float(f["close"]),
            "tqqq_reference_price": float(latest_paper["tqqq_close"]) if latest_paper and latest_paper.get("tqqq_close") else None,
            "price_session": latest_paper.get("session_date") if latest_paper else None,
            "source": latest_paper.get("execution_source") if latest_paper else None,
        },
        "paper": {
            "status": "ACTIVE" if latest_paper else "WAITING_FOR_FIRST_PROSPECTIVE_EXECUTION",
            "latest": latest_paper, "sessions": len(paper_rows), "trades": len(trades),
            "equity_history": [{"date":r.get("session_date"),"equity":float(r.get("equity",0)),"drawdown":float(r.get("drawdown",0)),"return":float(r.get("cumulative_return",0))} for r in paper_rows[-180:]],
            "recent_trades": trades[-20:],
        },
        "performance": performance,
        "readiness": readiness,
        "market_context": market_context,
        "risk_context": risk_context,
        "data_quality": data_quality,
        "benchmark": benchmark,
        "event_journal": event_journal,
        "regime_analytics": regime_analytics,
        "change_digest": change_digest,
        "daily_digest": daily_digest,
        "slo": slo,
        "transition_explanation": transition_explanation,
        "evidence_maturity": evidence_maturity,
        "risk_telemetry": risk_telemetry,
        "experiment_quality": experiment_quality,
        "anomalies": anomalies,
        "recovery_plan": recovery_plan,
        "data_provenance": data_provenance,
        "forward_path": forward_path,
        "execution_quality": execution_quality,
        "forward_quality": forward_quality,
        "qc_parity_dossier": qc_parity_dossier,
        "execution_plan": execution_plan,
        "trade_receipts": trade_receipts,
        "execution_audit": execution_audit,
        "cost_attribution": cost_attribution,
        "execution_readiness": execution_readiness,
        "automation_guard": automation_guard,
        "execution_cockpit": execution_cockpit,
        "execution_policy": execution_policy,
        "capital_readiness":capital_readiness,
        "prospective_maturity":prospective_maturity,
        "incident_state": incident_state,
        "publication_gate": publication_gate,
        "artifact_integrity": artifact_integrity,
        "research_provenance": research_provenance,
        "dependency_integrity": dependency_integrity,
        "context_quality": context_quality,
        "context_analytics": context_analytics,
        "data_provenance": data_provenance,
        "stress_scenarios": stress_scenarios,
        "exposure": exposure,
        "drawdown_budget": drawdown_budget,
        "integrity": {
            "health": health, "nonmaterial_input_revisions": len(revision_rows),
            "qc_reference": "LOCKED", "yahoo_replay": "DATA_SOURCE_DRIFT_DIAGNOSTIC",
            "parity": {
                "qc_daily_states_locked": parity_manifest.get("sessions"),
                "python_daily_recomputation_proven": parity_manifest.get("python_daily_recomputation_proven",False),
                "missing_for_full_1_to_1": parity_manifest.get("missing_for_full_1_to_1",[]),
                "diagnostic_status": parity_audit.get("status","PENDING"),
                "diagnostic_scope": parity_audit.get("recomputation_scope","PENDING"),
                "transition_match_rate": parity_audit.get("transition_match_rate"),
                "session_coverage_vs_qc_reference": parity_audit.get("session_coverage_vs_qc_reference"),
            },
        },
        "qc_frozen_record": {
            "status": "LEGACY_REFERENCE_UNVERIFIED_BY_CURRENT_PUBLICATION",
            "period": "2009-09 through 2024-08",
            "metrics": None,
            "evidence_scope": "LEGACY_FROZEN_REFERENCE_REQUIRES_CANONICAL_PROVENANCE_ARTIFACT",
            "full_daily_python_parity_proven": False,
            "automatic_claim_authorized": False
        },
        "historical_context": historical,
        "why": why,
        "signal_history": signal_tail,
        "history_90": history_tail,
    }
    mp=Path(mobile_data_path); mp.parent.mkdir(parents=True,exist_ok=True)
    mp.write_text(json.dumps(mobile,indent=2,default=str)+"\n",encoding="utf-8")
    return text


def main() -> int:
    print(build_dashboard())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""StockLens live-readiness evidence audit.

A technically valid backtest is NEVER sufficient evidence for live trading.
This module makes missing evidence machine-readable without inventing fills,
out-of-sample statistics, approvals, or automatic broker authorization.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from observed_tqqq_only_gate import check as require_observed_etf
from tradable_tqqq_execution_validate import validate as validate_etf_report

OUT = "docs/backtest_live_readiness.json"
RESEARCH_OUT = "research/backtest_live_readiness.json"

# These are operational evidence collection checkpoints, not statistical proof.
REVIEW_PAIRED_SESSION_FLOOR = 63
EXTENDED_PAIRED_SESSION_FLOOR = 252


def _load(path: str, default=None):
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else (default or {})


def evaluate(*, report, capital, benchmark, paper_gap, workbench, observation,
             policy, health, source_proof):
    checks = []
    def add(key, category, passed, description, evidence, severity="REQUIRED"):
        checks.append({"id": key, "category": category,
                       "status": "PASS" if passed else "BLOCKED",
                       "description": description, "evidence": evidence,
                       "severity": severity})
    period = report.get("period") or {}
    pure = report.get("no_contributions") or {}
    base = pure.get("stocklens") or {}
    qqq = pure.get("qqq_buy_hold") or {}
    monthly = report.get("initial_100k_monthly_3500") or {}
    market = health.get("market_session") or {}
    full_lean = workbench.get("full_lean_export") or {}
    sig = capital.get("prospective_evidence") or {}
    paired = int(paper_gap.get("paired_sessions") or 0)
    paper_sessions = int(paper_gap.get("paper_sessions") or 0)
    pro_sessions = int(capital.get("prospective_completed_sessions") or 0)
    benchmark_sessions = int(benchmark.get("sessions") or 0)

    add("OBSERVED_ETF_HISTORY", "Backtest data",
        report.get("status") == "PASS"
        and report.get("observed_instruments") == ["QQQ", "TQQQ"]
        and policy.get("never_fallback_to_synthetic") is True
        and period.get("start", "") >= "2010-02-09"
        and int(period.get("sessions") or 0) >= 3000,
        "Observed QQQ/TQQQ daily prices only, matched inception and sessions.",
        {"period": period, "source": report.get("price_source"),
         "data_sha256": report.get("price_fingerprint_sha256")})

    add("MATCHED_QQQ_BENCHMARK", "Backtest data",
        pure.get("start") == period.get("start")
        and pure.get("end") == period.get("end")
        and base.get("paid_capital") == qqq.get("paid_capital")
        and (monthly.get("stocklens") or {}).get("paid_capital") ==
            (monthly.get("qqq_buy_hold") or {}).get("paid_capital"),
        "Both strategies require identical market dates and external cashflows.",
        {"stocklens": base.get("ending_equity"), "qqq": qqq.get("ending_equity"),
         "contribution_matched": (monthly.get("stocklens") or {}).get("paid_capital") ==
                                  (monthly.get("qqq_buy_hold") or {}).get("paid_capital")})

    add("BACKTEST_STRESS_COMPUTED", "Backtest model",
        len(report.get("slippage_stress_no_contributions") or []) >= 5
        and len(report.get("signal_lag_stress_no_contributions") or []) >= 3,
        "Fee/slippage and extra decision-lag scenarios must be computed, not assumed.",
        {"slippage_cases": len(report.get("slippage_stress_no_contributions") or []),
         "decision_lag_cases": len(report.get("signal_lag_stress_no_contributions") or [])})

    add("LIVE_EXECUTION_TIME_PARITY", "Execution reality", False,
        "Daily adjusted OPEN is not an observed 09:31/09:32 execution price. Obtain verified minute-bar and fill evidence.",
        {"observed_0931_0932_fills": report.get("intraday_0931_0932_fills_observed"),
         "execution_proxy": report.get("execution_policy")})

    add("RAW_LEAN_SAME_RUN_EXPORT", "Reproducibility",
        full_lean.get("execution_parity_ready") is True
        and full_lean.get("status") == "PASS",
        "Require exact code/data identity and full original LEAN daily equity, orders, cashflow and fill exports.",
        {"status": full_lean.get("status", "MISSING"),
         "errors": full_lean.get("errors", [])})

    add("POINT_IN_TIME_AND_PROVIDER_AUDIT", "Reproducibility",
        source_proof.get("verified_independent_price_provider") is True
        and source_proof.get("corporate_actions_independently_reconciled") is True
        and source_proof.get("raw_vendor_snapshots_immutable") is True,
        "Independent adjusted-price vendor crosscheck, durable raw snapshots, corporate-action and availability-time audit.",
        {"observed_source": report.get("price_source"), "independent_vendor": "NOT_VERIFIED",
         "price_adjustment_audit": "NOT_VERIFIED"})

    add("RESEARCH_SELECTION_AUDIT", "Statistical validity", False,
        "Audit all parameter searches, failed variants, selection count, multiple testing, and previously used holdouts.",
        {"status": "NOT_INDEPENDENTLY_AUDITED", "frozen_baseline": report.get("baseline")})

    add("PRE_REGISTERED_INDEPENDENT_FORWARD", "Statistical validity", False,
        "Prospective frozen StockLens 8.0, tracked AFTER registration, must be independently reviewed before live deployment.",
        {"sl9_challenger_sessions_not_baseline_proof": pro_sessions,
         "prospective_baseline_verified_sessions": paper_sessions,
         "requested_review_checkpoints": [REVIEW_PAIRED_SESSION_FLOOR, EXTENDED_PAIRED_SESSION_FLOOR]})

    add("PAPER_EXECUTION_SESSIONS", "Forward paper",
        paper_sessions >= REVIEW_PAIRED_SESSION_FLOOR,
        "Record at least 63 completed paper execution sessions to begin a formal review, not to establish guaranteed profitability.",
        {"paper_sessions": paper_sessions, "review_floor": REVIEW_PAIRED_SESSION_FLOOR})

    add("PAPER_REPLAY_PAIRED_ATTRIBUTION", "Forward paper",
        paper_gap.get("status") in ("PASS", "ACTIVE")
        and paired >= REVIEW_PAIRED_SESSION_FLOOR
        and paper_gap.get("component_attribution", {}).get("status") == "IDENTIFIED",
        "Observed paper equity and modeled replay must be compared for identical sessions, costs, lag and residual causes.",
        {"paired_sessions": paired, "gap_status": paper_gap.get("status"),
         "component_attribution": paper_gap.get("component_attribution", {}).get("status")})

    add("PROSPECTIVE_QQQ_BENCHMARK", "Forward paper",
        benchmark.get("status") in ("PASS", "ACTIVE")
        and benchmark_sessions >= REVIEW_PAIRED_SESSION_FLOOR
        and benchmark.get("stocklens_return") is not None
        and benchmark.get("qqq_return") is not None,
        "Real time-matched forward paper P&L versus QQQ net of modeled costs; never substitute challenger returns.",
        {"benchmark_sessions": benchmark_sessions, "benchmark_status": benchmark.get("status")})

    add("BROKER_SANDBOX_DRY_RUN", "Broker operations",
        observation.get("broker_sandbox_contract_tests") is True
        and observation.get("idempotency_replay_verified") is True
        and observation.get("reconciliation_verified") is True
        and observation.get("kill_switch_verified") is True,
        "Test idempotent order submission, rejects, partial fills, reconnect, reconciliation and emergency kill-switch in sandbox.",
        {"status": "NOT_VERIFIED", "orders_sent": False})

    add("DECISION_MONITORING_AND_STALE_DATA", "Operations",
        health.get("status") == "HEALTHY"
        and health.get("market_session_freshness") == "CURRENT"
        and market.get("signal_replay_aligned") is True,
        "Same-day exchange-calendar and source freshness, signal/replay alignment and fail-closed monitoring.",
        {"health": health.get("status"), "market_freshness": health.get("market_session_freshness")})

    add("RISK_LIMITS_AND_GAP_CONTROLS", "Risk governance", False,
        "Human-approved loss budget, position sizing, concentration, volatility gap limits, kill switch and response playbook must be validated.",
        {"historical_max_drawdown": base.get("max_drawdown"),
         "stress_loss_guarantee": False,
         "policy": "NOT_YET_APPROVED"})

    add("HUMAN_CAPITAL_AND_COMPLIANCE_APPROVAL", "Risk governance", False,
        "Independent human acceptance of risk, broker/account jurisdiction constraints and explicit capital authorization required.",
        {"automated_live_authorization": False, "capital_scaled_ready": capital.get("scaled_capital_ready")})

    blockers = [c["id"] for c in checks if c["status"] != "PASS"]
    # This status is NEVER inferred from a high backtested CAGR.
    return {
        "schema_version": 1, "kind": "STOCKLENS_LIVE_READINESS",
        "status": "BLOCKED_FOR_LIVE_TRADING",
        "model": "StockLens 8.0 FROZEN",
        "evidence_class": "OBSERVED_ETF_DAILY_OPEN_PROXY_NOT_BROKER_LIVE",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "backtest_window": period,
        "historical_observed_etf_cagr": base.get("cagr_without_contributions"),
        "historical_qqq_cagr": qqq.get("cagr_without_contributions"),
        "historical_max_drawdown": base.get("max_drawdown"),
        "statistical_significance_not_proven": True,
        "observed_daily_open_not_true_fills": True,
        "prospective_challenger_sessions": pro_sessions,
        "prospective_frozen_paper_sessions": paper_sessions,
        "paired_forward_paper_sessions": paired,
        "review_floors_are_not_proof": True,
        "checks": checks,
        "passed_count": len(checks) - len(blockers),
        "blocked_count": len(blockers),
        "blockers": blockers,
        "automated_live_trading_authorized": False,
        "automatic_model_promotion": False,
        "capital_scaling_authorized": False,
        "claim": "Backtest integrity can be high while live trading remains unproven. "
                 "No historical, paper or sample checkpoint alone implies a future-return guarantee.",
    }


def build(out=OUT, research_out=RESEARCH_OUT):
    # Always fail CI if canonical real-TQQQ evidence becomes synthetic or corrupted.
    require_observed_etf()
    validate_etf_report()
    report = _load("research/tradable_tqqq_execution_comparison.json")
    policy = _load("research/OBSERVED_TQQQ_ONLY_POLICY.json")
    result = evaluate(
        report=report, policy=policy,
        capital=_load("docs/capital_readiness.json"),
        benchmark=_load("shadow_history/benchmark.json"),
        paper_gap=_load("docs/backtest_paper_gap.json"),
        workbench=_load("docs/workbench.json"),
        observation=_load("docs/execution_observation.json"),
        health=_load("docs/workbench_evidence_health.json"),
        source_proof=_load("research/verified_price_source_audit.json"),
    )
    for dest in (out, research_out):
        target = Path(dest)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": result["status"], "passed": result["passed_count"],
                      "blocked": result["blocked_count"], "blockers": result["blockers"]}))
    return result


if __name__ == "__main__":
    build()

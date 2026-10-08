"""Fail-closed parity between the exact frozen 8.0 Shadow decision and ETF backtest.

The comparison is based on the same QQQ close and identical model outputs.
It does not equate daily adjusted OPEN with the paper 09:31/09:32 fill.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

REPORT = "research/tradable_tqqq_execution_comparison.json"
SIGNAL = "output/latest_signal.json"
OUT = "shadow_history/frozen_decision_parity.json"


def compare(report: dict, signal: dict) -> dict:
    candidate = report.get("latest_frozen_decision") or {}
    actual = signal.get("latest") or {}
    errors = []
    if report.get("status") != "PASS" or report.get("observed_instruments") != ["QQQ", "TQQQ"]:
        errors.append("NOT_OBSERVED_ETF_BACKTEST")
    if candidate.get("decision_source") != "stocklens.core.replay_levels":
        errors.append("UNCERTIFIED_DECISION_ENGINE")
    if signal.get("mode") != "SHADOW_ONLY_NO_BROKER_ACTIONS":
        errors.append("BROKER_MODE_UNEXPECTED")
    if signal.get("state_replay") != "EXACT_FROM_2009_09_01_WITH_PRESTART_WARMUP":
        errors.append("STATE_REPLAY_CONTRACT_CHANGED")
    if candidate.get("asof_date") != report.get("period", {}).get("end"):
        errors.append("BACKTEST_SIGNAL_DATE_NOT_LATEST")
    if actual.get("asof_date") != candidate.get("asof_date"):
        errors.append("SIGNAL_DATE_MISMATCH")
    for field in ("level", "defense_active"):
        if type(actual.get(field)) is not type(candidate.get(field)) or actual.get(field) != candidate.get(field):
            errors.append(field.upper() + "_MISMATCH")
    for field in ("target_leverage", "qqq_weight", "tqqq_weight", "invested_fraction"):
        a, b = actual.get(field), candidate.get(field)
        if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
            errors.append(field.upper() + "_MISSING")
        elif not (math.isfinite(float(a)) and math.isfinite(float(b)) and
                  math.isclose(float(a), float(b), rel_tol=0, abs_tol=1e-10)):
            errors.append(field.upper() + "_MISMATCH")
    observed_close = candidate.get("qqq_adjusted_close")
    live_close = (actual.get("features") or {}).get("close")
    audit_close = (signal.get("data_audit") or {}).get("last_close")
    if any(not isinstance(x, (int, float)) or not math.isfinite(float(x)) for x in
           (observed_close, live_close, audit_close)):
        errors.append("QQQ_ADJUSTED_CLOSE_MISSING")
    elif not all(math.isclose(float(observed_close), float(x), rel_tol=0, abs_tol=1e-7)
                 for x in (live_close, audit_close)):
        errors.append("QQQ_ADJUSTED_CLOSE_DRIFT")
    for field in ("qqq_weight", "tqqq_weight"):
        if float(actual.get(field) or 0) < 0:
            errors.append(field.upper() + "_NEGATIVE")
    if signal.get("execution_plan", {}).get("broker_actions_enabled") is not False:
        errors.append("LIVE_BROKER_ACTIONS_NOT_DISABLED")
    result = {
        "schema_version": 1,
        "status": "PASS" if not errors else "FAIL",
        "signal_asof": actual.get("asof_date"),
        "research_asof": candidate.get("asof_date"),
        "equal_frozen_target": not errors,
        "decision_engine": "stocklens.core.replay_levels",
        "observed_etf_prices_required": True,
        "broker_orders_authorized": False,
        "intraday_execution_parity_proven": False,
        "limitations": "Only decision equality is checked; actual fills, daily OPEN and 09:31/09:32 differ.",
        "errors": errors,
    }
    return result


def validate(report_path=REPORT, signal_path=SIGNAL, out=OUT):
    r = json.loads(Path(report_path).read_text(encoding="utf-8"))
    s = json.loads(Path(signal_path).read_text(encoding="utf-8"))
    result = compare(r, s)
    dest = Path(out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["status"] != "PASS":
        raise RuntimeError("FROZEN_BACKTEST_SHADOW_DECISION_DIVERGENCE:" + ",".join(result["errors"]))
    return result


if __name__ == "__main__":
    validate()

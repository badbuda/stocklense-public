"""Risk audit based exclusively on the observed-ETF execution-proxy NAV path.

No QQQ-return-times-leverage data, no invented broker fills, and no model retuning.
"""
from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

RESEARCH = "research/observed_tqqq_risk_audit.json"
PUBLIC = "docs/observed_tqqq_risk_audit.json"


def _maxdd(values, initial=100_000.0):
    peak = float(initial)
    worst = 0.0
    for value in values:
        peak = max(peak, value)
        worst = min(worst, value / peak - 1.0)
    return worst


def _subperiod(rows, begin, end):
    sub = [r for r in rows if begin <= r["date"] <= end]
    if len(sub) < 2:
        return None
    start, finish = sub[0], sub[-1]
    # Within-window returns use the same first mark; no invented cashflows.
    nav = [r["stocklens_nav"] for r in sub]
    qnav = [r["qqq_nav"] for r in sub]
    return {
        "start": start["date"], "end": finish["date"], "sessions": len(sub),
        "stocklens_return": nav[-1] / nav[0] - 1.0,
        "qqq_return": qnav[-1] / qnav[0] - 1.0,
        "stocklens_max_drawdown": _maxdd([v / nav[0] for v in nav], 1.0),
        "qqq_max_drawdown": _maxdd([v / qnav[0] for v in qnav], 1.0),
        "stocklens_better": nav[-1] / nav[0] > qnav[-1] / qnav[0],
    }


def evaluate(report: dict) -> dict:
    if (report.get("observed_instruments") != ["QQQ", "TQQQ"] or
        report.get("broker_fills_observed") is not False or
        report.get("automatic_model_promotion") is not False):
        raise ValueError("UNVERIFIED_OBSERVED_INSTRUMENT_REPORT")
    cohort = report.get("no_contributions", {})
    path = cohort.get("daily_nav_rows") or []
    if len(path) < 3 or len(path) != cohort.get("sessions"):
        raise ValueError("MISSING_FULL_OBSERVED_ETF_NAV_PATH")
    dates = [x.get("date") for x in path]
    if any(not isinstance(x, str) for x in dates) or dates != sorted(set(dates)):
        raise ValueError("DUPLICATE_OR_REORDERED_NAV_DATES")
    if dates[0] != cohort["start"] or dates[-1] != cohort["end"]:
        raise ValueError("MISMATCHED_COHORT_BOUNDARIES")
    for row in path:
        if any(not isinstance(row.get(k), (float, int)) or
               not math.isfinite(float(row[k])) or row[k] <= 0
               for k in ("stocklens_nav", "qqq_nav")):
            raise ValueError("INVALID_NAV_VALUES")
    first, last = path[0], path[-1]
    benchmark = cohort["qqq_buy_hold"]
    strategy = cohort["stocklens"]
    if not (math.isclose(last["stocklens_nav"], strategy["ending_equity"], rel_tol=0, abs_tol=1e-5) and
            math.isclose(last["qqq_nav"], benchmark["ending_equity"], rel_tol=0, abs_tol=1e-5)):
        raise ValueError("ENDPOINT_NAV_PROVENANCE_DRIFT")
    if cohort.get("monthly_contribution") != 0:
        raise ValueError("CONTRIBUTIONS_NOT_EXCLUDED_FROM_PATH")
    if (abs(_maxdd([x["stocklens_nav"] for x in path]) - strategy["max_drawdown"]) > 1e-8 or
        abs(_maxdd([x["qqq_nav"] for x in path]) - benchmark["max_drawdown"]) > 1e-8):
        raise ValueError("DRAWDOWN_PATH_DISAGREEMENT")
    rolling = {}
    for width in (21, 63, 126, 252, 756, 1260):
        all_windows = []
        # Every 21 sessions, not independent windows or p-values.
        for start in range(0, len(path) - width, 21):
            finish = start + width
            a, b = path[start], path[finish]
            sl = b["stocklens_nav"] / a["stocklens_nav"] - 1.0
            q = b["qqq_nav"] / a["qqq_nav"] - 1.0
            all_windows.append({
                "start": a["date"], "end": b["date"],
                "stocklens_return": sl, "qqq_return": q,
                "relative_return_pp": 100 * (sl - q),
            })
        if all_windows:
            worst = min(all_windows, key=lambda r: r["stocklens_return"])
            rolling[str(width) + "_sessions"] = {
                "window_count": len(all_windows),
                "stocklens_beats_qqq": sum(r["stocklens_return"] > r["qqq_return"] for r in all_windows),
                "stocklens_loses_qqq": sum(r["stocklens_return"] <= r["qqq_return"] for r in all_windows),
                "worst_stocklens_window": worst,
                "worst_relative_return_pp": min(x["relative_return_pp"] for x in all_windows),
                "interpretation": "Overlapping observed ETF NAV windows; not independent holdouts or statistical proof.",
            }
    yearly = []
    for yr in sorted(set(d[:4] for d in dates)):
        part = _subperiod(path, yr+"-01-01", yr+"-12-31")
        if part:
            yearly.append({"year": int(yr), **part})
    crises = {}
    for tag, a, b in [
        ("2020_COVID_SHOCK", "2020-02-01", "2020-05-31"),
        ("2022_RATE_SHOCK", "2022-01-01", "2022-12-31"),
    ]:
        crises[tag] = _subperiod(path, a, b)
    return {
        "schema_version": 1, "kind": "OBSERVED_ETF_NAV_PATH_RISK_DIAGNOSTIC",
        "status": "PASS", "source_report_sha256": report["price_fingerprint_sha256"],
        "evidence_scope": "OBSERVED_QQQ_TQQQ_DAILY_OPEN_EXECUTION_PROXY",
        "no_synthetic_leverage": True, "no_broker_fills_claimed": True,
        "period": report["period"],
        "full_path": {
            "stocklens_max_drawdown": strategy["max_drawdown"],
            "qqq_max_drawdown": benchmark["max_drawdown"],
            "stocklens_cagr": strategy["cagr_without_contributions"],
            "qqq_cagr": benchmark["cagr_without_contributions"],
        },
        "rolling_windows": rolling,
        "calendar_years": yearly,
        "crisis_windows": crises,
        "statistical_independence_proven": False,
        "automatic_model_promotion": False,
        "automatic_broker_trading": False,
        "interpretation": "Observed ETF daily-open proxy risk diagnostics only; overlapping windows, reused historical regimes, unknown future fills and selection bias prohibit live-return claims.",
    }


def build(source="research/tradable_tqqq_execution_comparison.json",
          output=RESEARCH, public=PUBLIC):
    report = json.loads(Path(source).read_text(encoding="utf-8"))
    result = evaluate(report)
    for p in (output, public):
        out = Path(p)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"], "period": result["period"],
        "rolling_window_sizes": list(result["rolling_windows"]),
        "historical_not_live": True,
    }))
    return result


if __name__ == "__main__":
    build()

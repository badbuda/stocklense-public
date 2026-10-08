"""Observed-ETF-only paired daily NAV robustness diagnostics.

All inputs are actual QQQ/TQQQ ETF price-based execution-proxy NAVs.
Block resampling is a DESCRIPTIVE stability check, not a clean holdout, p-value
or proof of future alpha. The frozen StockLens 8.0 decision path is untouched.
"""
from __future__ import annotations

import hashlib
import json
import math
import random
from collections import defaultdict
from pathlib import Path

SRC = "research/tradable_tqqq_execution_comparison.json"
OUT = "research/observed_etf_statistical_robustness.json"
PUBLIC = "docs/observed_etf_statistical_robustness.json"
SEED = 801008
BOOTSTRAP_REPLICATIONS = 600


def _percentile(values, fraction):
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


def _block_bootstrap(relative_log, width, repeats, seed):
    """Paired moving-block bootstrap of relative log return, not an alpha p-value."""
    n = len(relative_log)
    if n < width * 2:
        raise ValueError("INSUFFICIENT_SESSIONS_FOR_BLOCK_RESAMPLING")
    prefix = [0.0]
    for x in relative_log:
        prefix.append(prefix[-1] + x)
    rng = random.Random(seed)
    possibilities = n - width + 1
    draws = math.ceil(n / width)
    sampled = []
    for _ in range(repeats):
        total = 0.0
        remaining = n
        for _ in range(draws):
            if remaining == 0:
                break
            start = rng.randrange(possibilities)
            take = min(width, remaining)
            total += prefix[start + take] - prefix[start]
            remaining -= take
        sampled.append(math.expm1(total / n * 252.0))
    return {
        "block_sessions": width,
        "replicates": repeats,
        "annualized_relative_log_growth_pctiles": {
            "p05": _percentile(sampled, 0.05),
            "p50": _percentile(sampled, 0.50),
            "p95": _percentile(sampled, 0.95),
        },
        "fraction_resamples_above_zero_NOT_P_VALUE": sum(v > 0 for v in sampled) / repeats,
        "scope": "IN_SAMPLE_PAIRED_BLOCK_RESAMPLING_NOT_HYPOTHESIS_TEST",
    }


def evaluate(report, *, bootstrap_reps=BOOTSTRAP_REPLICATIONS):
    if (report.get("kind") != "OBSERVED_QQQ_TQQQ_DAILY_OPEN_EXECUTION_PROXY"
            or report.get("observed_instruments") != ["QQQ", "TQQQ"]
            or report.get("full_lean_execution_parity") is not False
            or report.get("automatic_model_promotion") is not False):
        raise ValueError("SOURCE_NOT_OBSERVED_ETF_REPLAY")
    primary = report.get("no_contributions") or {}
    path = primary.get("daily_nav_rows") or []
    if len(path) < 1000 or len(path) != primary.get("sessions"):
        raise ValueError("MISSING_COMPLETE_OBSERVED_DAILY_PATH")
    if report.get("period", {}).get("sessions") != len(path):
        raise ValueError("SOURCE_WINDOW_MISMATCH")
    xs = []
    timestamps = []
    obs = []
    baseline = float(primary.get("stocklens", {}).get("paid_capital", 100000.0))
    benchmark = float(primary.get("qqq_buy_hold", {}).get("paid_capital", 100000.0))
    if (primary.get("monthly_contribution") != 0 or baseline != benchmark
            or baseline <= 0 or not math.isfinite(baseline)):
        raise ValueError("UNMATCHED_OR_CONTRIBUTED_INITIAL_CAPITAL")
    prev = {"date": "0000-00-00", "stocklens_nav": baseline, "qqq_nav": benchmark}
    for row in path:
        d = row.get("date")
        if not isinstance(d, str) or (prev and d <= prev["date"]):
            raise ValueError("NONMONOTONIC_DAILY_DATES")
        if row.get("effective_prior_signal_date", "") >= d:
            raise ValueError("LOOKAHEAD_AT_SESSION_MARK")
        a, b = float(row["stocklens_nav"]), float(row["qqq_nav"])
        if not (math.isfinite(a) and math.isfinite(b) and a > 0 and b > 0):
            raise ValueError("INVALID_DAILY_NAV")
        obs.append(f"{d},{a:.6f},{b:.6f}")
        if prev is not None:
            excess = math.log(a / float(prev["stocklens_nav"])) - math.log(b / float(prev["qqq_nav"]))
            xs.append(excess)
            timestamps.append(d)
        prev = row
    if path[0]["date"] != primary["start"] or path[-1]["date"] != primary["end"]:
        raise ValueError("MISMATCHED_DAILY_NAV_PERIOD")
    n = len(xs)
    total = sum(xs)
    growth_ratio = math.exp(total)
    if not math.isclose(growth_ratio, primary["ending_equity_ratio"], rel_tol=1e-6):
        raise ValueError("NAV_RELATIVE_GROWTH_MISMATCH")
    yearly = defaultdict(list)
    for d, x in zip(timestamps, xs):
        yearly[d[:4]].append(x)
    leave_year_out = []
    for year, observations in sorted(yearly.items()):
        remainder = n - len(observations)
        if remainder < 252:
            continue
        rel = math.expm1((total - sum(observations)) / remainder * 252.0)
        leave_year_out.append({"excluded_calendar_year": int(year),
                               "remaining_sessions": remainder,
                               "annualized_relative_log_growth": rel})
    top_positive = sorted((x for x in xs if x > 0), reverse=True)
    removals = {}
    for k in (1, 5, 10, 21, 63):
        remaining = total - sum(top_positive[:k])
        removals[str(k)] = {
            "relative_growth_without_top_positive_sessions": math.exp(remaining),
            "remaining_ann_relative_log_growth": math.expm1(252 * remaining / n),
        }
    replicates = {}
    for block in (21, 63, 126):
        replicates[str(block)] = _block_bootstrap(
            xs, block, bootstrap_reps, SEED + block
        )
    worst = min(xs)
    best = max(xs)
    return {
        "schema_version": 1,
        "status": "PASS",
        "kind": "OBSERVED_ETF_HISTORICAL_PAIRED_RESAMPLING",
        "source_evidence_class": "TRADEABLE_ETF_HISTORICAL_PRICE_EXECUTION_PROXY",
        "source_price_sha256": report["price_fingerprint_sha256"],
        "full_nav_sha256": hashlib.sha256(("\n".join(obs) + "\n").encode()).hexdigest(),
        "period": report["period"],
        "daily_relative_log_observations": n,
        "original_relative_ending_wealth_ratio": growth_ratio,
        "original_annualized_relative_log_growth": math.expm1(total / n * 252),
        "best_single_day_relative_log_return": best,
        "worst_single_day_relative_log_return": worst,
        "paired_moving_block_bootstrap": replicates,
        "leave_one_calendar_year_out": leave_year_out,
        "positive_day_concentration_sensitivity": removals,
        "synthetic_leverage_used": False,
        "automatic_model_promotion": False,
        "live_broker_authorized": False,
        "clean_out_of_sample_test": False,
        "statistical_significance_proven": False,
        "interpretation": (
            "All periods and bootstrap resamples reuse the historical research "
            "sample selected to develop and review this model. Bootstrap stability "
            "does not correct researcher degrees of freedom, survivorship, "
            "lookahead in original parameter selection, or brokerage fill differences. "
            "Percentile bands and positive-sample frequencies are NOT p-values "
            "or a guarantee of future excess returns."
        ),
    }


def build(source=SRC, output=OUT, public=PUBLIC):
    report = json.loads(Path(source).read_text(encoding="utf-8"))
    result = evaluate(report)
    for name in (output, public):
        path = Path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": result["status"], "sessions": result["period"]["sessions"],
        "bootstrap_blocks": list(result["paired_moving_block_bootstrap"]),
        "independent_oos": False,
    }))
    return result


if __name__ == "__main__":
    build()

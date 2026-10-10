"""Volatility-drag-aware downside research with real observed QQQ/TQQQ daily opens.

Never changes StockLens 8.0 frozen signal. No synthetic 3x returns, broker
quotes, actual fills, leverage borrowing, forward promise, or model promotion.
Every overlay uses ONLY already-completed QQQ close data, executed next session
at modeled Yahoo adjusted daily OPEN, whole shares plus fee/slippage.
"""
from __future__ import annotations

from datetime import date
import json
import math
from pathlib import Path
from statistics import stdev

from observed_etf_two_question_audit import (
    FEE_BPS, SLIP_BPS, SPLITS, START_CAPITAL,
    _metrics, _prices, _run as reference_frozen, load,
)
from stocklens.core import TARGET_INVESTED_FRACTION, weights_for_leverage
from tradable_tqqq_execution_comparison import _mark, _rebalance

OUT = Path("research/results/vol60_ramped_reentry_observed_open.json")
REPORT = Path("research/reports/vol60_ramped_reentry_observed_open.md")
MODES = (
    "frozen",
    "vol60_instant",
    "vol60_ramp5",
    "vol60_ramp10",
    "vol60_hold5_ramp5",
    "vol60_hold10_ramp10",
    "vol60_shock_ramp5",
)
# Not optimized against outcome: physically interpretable continuation of
# previously fixed 60% annualized volatility target, plus 5/10 session ramps.
# Cap floor is 1x invested QQQ when frozen has exposure; 0x frozen stays 0.
PREDECLARED = {
    "frozen": (0, 0, False),
    "vol60_instant": (0, 0, False),
    "vol60_ramp5": (5, 0, False),
    "vol60_ramp10": (10, 0, False),
    "vol60_hold5_ramp5": (5, 5, False),
    "vol60_hold10_ramp10": (10, 10, False),
    "vol60_shock_ramp5": (5, 0, True),
}
LAGS = (0, 1, 2)
SLIPPAGE_BPS = (10., 20., 30.)
FEE_BPS_FIXED = 2.
BAND = .005
CLOSE_EPS = 1e-9


def _features(rows):
    """Index t only reads QQQ closes at or before completed day t."""
    closes = [float(r["qc"]) for r in rows]
    rv20 = [None] * len(closes)
    shock = [False] * len(closes)
    # Rolling 20 close-to-close QQQ LOG returns; not synthetic TQQQ P&L.
    for t in range(20, len(closes)):
        returns = [math.log(closes[k] / closes[k - 1])
                   for k in range(t - 19, t + 1)]
        rv20[t] = stdev(returns) * math.sqrt(252)
        shock[t] = any(closes[j] / closes[j - 5] - 1 <= -.07
                       for j in range(max(5, t - 4), t + 1))
    return rv20, shock


def _raw_cap(rv20, shocks, observed_idx, with_shock=False):
    """Unknown warmup means no voluntary cap; missing data never trades."""
    if observed_idx < 0 or rv20[observed_idx] is None:
        return 3.0
    volatility = rv20[observed_idx]
    if not math.isfinite(volatility) or volatility < 0:
        raise ValueError("INVALID_PRIOR_COMPLETED_VOLATILITY")
    cap = min(3.0, max(1.0, .60 / max(volatility, 1e-8)))
    if with_shock and shocks[observed_idx]:
        cap = min(cap, 2.0)
    return cap


def _weights(exposure):
    if exposure <= 0:
        return {"QQQ": 0., "TQQQ": 0.}
    a, b = weights_for_leverage(exposure)
    return {"QQQ": a * TARGET_INVESTED_FRACTION,
            "TQQQ": b * TARGET_INVESTED_FRACTION}


def _weight_gap(shares, prices, weights, equity):
    return max(abs(shares[s] * prices[s]["open"] / equity - weights[s])
               for s in ("QQQ", "TQQQ"))


def simulate(rows, *, mode="frozen", lag=0, slippage_bps=SLIP_BPS,
             fee_bps=FEE_BPS_FIXED, check_prices=True):
    """Execute independent whole-share portfolios; no future signal access.

    The lag delays availability of observed historical QQQ volatility, NOT
    the frozen decision (whose timing is already encoded by prior signal).
    Downside cap cuts happen immediately when observed; upward cap recovery
    is held/released at a predeclared maximum leverage step per session.
    """
    if mode not in MODES or lag not in LAGS or slippage_bps not in SLIPPAGE_BPS:
        raise ValueError("UNREGISTERED_HYPOTHESIS_OR_STRESS")
    if not math.isfinite(fee_bps) or fee_bps < 0:
        raise ValueError("INVALID_FEE")
    if len(rows) < 3:
        raise ValueError("INSUFFICIENT_OBSERVED_COHORT")
    if check_prices:
        for row in rows:
            if not all(isinstance(row.get(key), (int, float)) and
                       math.isfinite(row[key]) and row[key] > 0
                       for key in ("qo", "qc", "to", "tc")):
                raise ValueError("INVALID_OBSERVED_OPEN_OR_CLOSE")
            if row.get("signal", "") >= row["date"]:
                raise ValueError("LOOKAHEAD_IN_FROZEN_SIGNAL")
    rv20, shocks = _features(rows)
    ramp, hold, include_shock = PREDECLARED[mode]
    p = {"cash": START_CAPITAL,
         "shares": {"QQQ": 0, "TQQQ": 0},
         "fees": 0., "slippage": 0., "trades": 0,
         "turnover_notional": 0.}
    navs, dates, levels = [], [], []
    interventions = 0
    skipped_bps = 0
    cap_state = 3.
    recovery_after = -1
    prev_level = None
    for i, row in enumerate(rows):
        frozen = float(row["l"])
        if frozen not in (0., 1.25, 2., 3.):
            raise ValueError("INVALID_FROZEN_LEVEL")
        if mode == "frozen":
            cap = cap_state = 3.
        else:
            raw_cap = _raw_cap(rv20, shocks, i - 1 - lag, include_shock)
            if raw_cap < cap_state - CLOSE_EPS:
                # Exit/derisk now; a new downward shock resets cooldown.
                cap_state = raw_cap
                recovery_after = i + hold
            elif raw_cap > cap_state + CLOSE_EPS:
                if i >= recovery_after:
                    cap_state = (raw_cap if ramp == 0
                                 else min(raw_cap, cap_state + 2. / ramp))
            cap = cap_state
        target = min(frozen, cap)
        if target > frozen + CLOSE_EPS:
            raise ValueError("OVERLAY_INCREASED_FROZEN_LEVERAGE")
        if target < frozen - CLOSE_EPS:
            interventions += 1
        prices = _prices(row)
        weights = _weights(target)
        execute = prev_level is None or abs(target - prev_level) > CLOSE_EPS
        if execute and prev_level is not None and mode != "frozen":
            current_nav = _mark(p, prices, "open")
            if current_nav <= 0:
                raise ValueError("INVALID_PRETRADE_ACCOUNT")
            # Rebalancing only if target changed AND away by >50bp;
            # not a claim of executable NBBO bid/ask.
            if _weight_gap(p["shares"], prices, weights, current_nav) <= BAND:
                execute = False
                skipped_bps += 1
        if execute:
            _rebalance(p, prices, weights, fee_bps, slippage_bps)
        equity = _mark(p, prices, "close")
        if equity <= 0 or not math.isfinite(equity) or p["cash"] < -1e-5:
            raise ValueError("BROKEN_PORTFOLIO_ACCOUNTING")
        navs.append(equity)
        dates.append(row["date"])
        levels.append(target)
        prev_level = target
    return {
        "stats": _metrics(navs, dates),
        "dates": dates, "navs": navs, "levels": levels,
        "intervention_sessions": interventions,
        "trades": p["trades"],
        "total_modeled_fee": p["fees"],
        "total_modeled_slippage": p["slippage"],
        "skipped_trades_due_to_50bp_band": skipped_bps,
        "observable_execution": "YAHOO_ADJUSTED_DAILY_OPEN_PROXY_NOT_09_31_NBBO",
        "actual_broker_fills_observed": False,
    }


def _window_metrics(path, start, end):
    indices = [i for i, day in enumerate(path["dates"]) if start <= day <= end]
    if len(indices) < 100:
        raise ValueError("INSUFFICIENT_SPLIT:" + start + ":" + end)
    a, b = indices[0], indices[-1]
    if indices != list(range(a, b+1)):
        raise ValueError("NONCONTIGUOUS_SPLIT")
    initial = START_CAPITAL if a == 0 else path["navs"][a - 1]
    # Derived from continuously simulated real whole-share portfolio, not
    # restarted/recalibrated independently at each historical subperiod.
    return _metrics(path["navs"][a:b + 1], path["dates"][a:b + 1], first=initial)


def _crisis_attribution(results):
    # Worst drawdown peak-to-trough defined on the independent frozen path.
    b = results["frozen"]
    peak = START_CAPITAL
    peak_date = b["dates"][0]
    best = {"max_drawdown": 0., "peak_date": peak_date, "trough_date": peak_date}
    for i, value in enumerate(b["navs"]):
        if value > peak:
            peak = value
            peak_date = b["dates"][i]
        drawdown = value / peak - 1.
        if drawdown < best["max_drawdown"]:
            best = {"max_drawdown": drawdown,
                    "peak_date": peak_date,
                    "trough_date": b["dates"][i]}
    start = b["dates"].index(best["peak_date"])
    end = b["dates"].index(best["trough_date"])
    for name, path in results.items():
        start_nav = START_CAPITAL if start == 0 else path["navs"][start - 1]
        best[name + "_same_dates_return"] = path["navs"][end] / start_nav - 1.
    return best


def evaluate(raw):
    rows = raw.get("daily", [])
    if len(rows) < 3000 or raw.get("observed_ohlc_available") is not True:
        raise ValueError("MISSING_OBSERVED_ETF_HISTORY")
    if raw.get("live_trading_authorized") is not False:
        raise ValueError("UNAUTHORIZED_SOURCE")
    baseline = reference_frozen(rows, variant="frozen")
    frozen = simulate(rows, mode="frozen")
    if len(baseline["navs"]) != len(frozen["navs"]):
        raise ValueError("FROZEN_REPLAY_LENGTH_DRIFT")
    for a, b in zip(baseline["navs"], frozen["navs"]):
        if not math.isclose(a, b, abs_tol=1e-5, rel_tol=1e-10):
            raise ValueError("FROZEN_REPLAY_DAILY_NAV_DRIFT")
    if not math.isclose(frozen["stats"]["max_drawdown"],
                        baseline["stats"]["max_drawdown"], abs_tol=1e-8):
        raise ValueError("FROZEN_REPLAY_DRAWDOWN_DRIFT")
    reference = raw["without_contributions"]["strategy"]
    if abs(frozen["stats"]["cagr"] - reference["cagr_without_contributions"]) > .001:
        raise ValueError("FROZEN_CAGR_PROVENANCE_DRIFT")
    results = {name: simulate(rows, mode=name) for name in MODES}
    base = results["frozen"]["stats"]
    summary = {}
    for name, path in results.items():
        x = path["stats"]
        summary[name] = {
            **x, "cagr_delta_pp": (x["cagr"] - base["cagr"]) * 100,
            "maxdd_improvement_pp": (x["max_drawdown"] - base["max_drawdown"]) * 100,
            "wealth_retained_vs_frozen": x["ending_equity"] / base["ending_equity"],
            "intervention_sessions": path["intervention_sessions"],
            "trades": path["trades"],
            "total_modeled_fee": path["total_modeled_fee"],
            "total_modeled_slippage": path["total_modeled_slippage"],
            "skipped_trades_due_to_50bp_band": path["skipped_trades_due_to_50bp_band"],
        }
    split_results = {}
    for label, (start, end) in SPLITS.items():
        metrics = {name: _window_metrics(path, start, end)
                   for name, path in results.items()}
        b = metrics["frozen"]
        split_results[label] = {
            name: {**value,
                   "cagr_delta_pp": 100 * (value["cagr"] - b["cagr"]),
                   "maxdd_improvement_pp": 100 * (value["max_drawdown"] -
                                                   b["max_drawdown"])}
            for name, value in metrics.items()
        }
    stress = []
    for name in MODES:
        for lag in LAGS:
            for slip in SLIPPAGE_BPS:
                path = simulate(rows, mode=name, lag=lag, slippage_bps=slip)
                st = path["stats"]
                stress.append({
                    "variant": name, "lag_sessions": lag,
                    "slippage_per_side_bps": slip,
                    "cagr": st["cagr"], "max_drawdown": st["max_drawdown"],
                    "ending_equity": st["ending_equity"],
                    "trades": path["trades"],
                    "intervention_sessions": path["intervention_sessions"],
                })
    # Do not cherry-pick one historical scenario and call it an investable winner.
    gates = {}
    for name in MODES[1:]:
        required = [x for x in stress if x["variant"] == name and
                    x["lag_sessions"] in (0, 1) and
                    x["slippage_per_side_bps"] in (10., 20.)]
        assert len(required) == 4
        approved_sensitivity = []
        for x in required:
            matching = next(b for b in stress if b["variant"] == "frozen" and
                            b["lag_sessions"] == x["lag_sessions"] and
                            b["slippage_per_side_bps"] == x["slippage_per_side_bps"])
            approved_sensitivity.append(
                x["max_drawdown"] - matching["max_drawdown"] >= .03
                and x["cagr"] - matching["cagr"] >= -.015
                and x["ending_equity"] / matching["ending_equity"] >= .8)
        gates[name] = {
            "historical_continue_gate": all(approved_sensitivity),
            "passed_stress_scenarios": sum(approved_sensitivity),
            "required_scenarios": 4,
            "threshold": "MaxDD >=3pp better, CAGR <=1.5pp worse, wealth >=80% baseline at lag0/1 and slippage10/20bps",
            "automatic_promotion_authorized": False,
        }
    return {
        "schema_version": 1,
        "kind": "VOL60_RAMPED_REENTRY_NEXT_OPEN_OBSERVED_ETF_RESEARCH_ONLY",
        "status": "RESEARCH_COMPUTED_NOT_FORWARD_VALIDATED",
        "source_path": "docs/portal-history.json",
        "source_snapshot_sha256": raw.get("snapshot_sha256"),
        "period": raw.get("period"),
        "frozen_strategy_changed": False,
        "synthetic_tqqq_used": False,
        "independent_bid_ask_proven": False,
        "original_lean_parity_proven": False,
        "clean_prospective_oos": False,
        "capital_deployment_authorized": False,
        "model_automatically_promoted": False,
        "source_semantics": "Yahoo observed adjusted QQQ/TQQQ daily OPEN proxy, no intraday broker fills",
        "costs": {"fees_bps_per_side": FEE_BPS_FIXED,
                  "base_slippage_bps_per_side": SLIP_BPS,
                  "stress_slippage_bps_per_side": list(SLIPPAGE_BPS)},
        "hypotheses_declared_before_outcome_review": PREDECLARED,
        "all_variants": list(MODES),
        "full_period_results": summary,
        "split_results_no_portfolio_restart": split_results,
        "cost_lag_stress": stress,
        "robustness_gate": gates,
        "frozen_worst_episode_same_dates": _crisis_attribution(results),
        "readme": [
            "Historical research sample previously explored extensively, not independent validation.",
            "Vol cap has a hard 1x floor if frozen exposure is nonzero. All overlays only reduce frozen leverage.",
            "Daily volatility derived from 20 PREVIOUS completed QQQ log returns; lag delays availability by 0/1/2 additional sessions.",
            "Vol cap fall acted on immediately, subsequent rise limited to .4x or .2x per day and optional five/ten-session hold.",
            "Comparative trade engine uses actual observed ETF prices only, while modeled daily opens/fees/slippage are not broker fills.",
            "Split metrics are windows of an uninterrupted NAV path, no model reboot at arbitrary boundaries.",
            "All reported gates are historical continuation screens, never authorization to promote capital or model.",
        ],
    }


def human_report(r):
    score = r["full_period_results"]
    fmt = lambda z: f"{100*z:.2f}%"
    b = score["frozen"]
    out = [
        "# StockLens 8.0: continuous Vol60 + gradual re-entry — research only",
        "",
        "No frozen-model modification. All estimates use real observed QQQ and TQQQ Yahoo-adjusted DAILY OPEN/CLOSE",
        f'({r["period"]["start"]} to {r["period"]["end"]}); not 09:31/09:32 NBBO or broker fills.',
        "",
        "## Same-accounting comparison: per-side 2bps fee + 10bps modeled slip",
        "",
        "| Mode | CAGR | MaxDD | CAGR delta pp | MaxDD gain pp | intervention sessions | trades |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for name in MODES:
        row = score[name]
        out.append(f'| {name} | {fmt(row["cagr"])} | {fmt(row["max_drawdown"])} | '
                   f'{row["cagr_delta_pp"]:+.2f} | {row["maxdd_improvement_pp"]:+.2f} | '
                   f'{row["intervention_sessions"]} | {row["trades"]} |')
    out += ["", "## Reused-period transfer (not pristine OOS)", ""]
    for label, block in r["split_results_no_portfolio_restart"].items():
        out.append("### " + label)
        out.append("| Mode | CAGR delta pp | MaxDD gain pp |")
        out.append("|---|---:|---:|")
        for name in MODES[1:]:
            row = block[name]
            out.append(f'| {name} | {row["cagr_delta_pp"]:+.2f} | {row["maxdd_improvement_pp"]:+.2f} |')
        out.append("")
    out += [
        "## Continuation gates and lag/cost falsification", "",
        "Continuation requires >=3pp DD improvement, <=1.5pp CAGR loss, >=80% ending wealth",
        "against frozen in **all** lag 0/1 and slippage 10/20 bps scenarios.",
    ]
    for name, v in r["robustness_gate"].items():
        out.append(f'- {name}: {v["passed_stress_scenarios"]}/4 scenarios; continue={v["historical_continue_gate"]}.')
    out += ["", "## Evidence boundary", "",
            "- Frozen model unchanged; no automatic challenger promotion.",
            "- Previously inspected historical samples cannot become independent forward tests by slicing.",
            "- No independent LEAN run, spread book, executable 09:31/09:32 quotes or broker fills.",
            "- Large drawdowns can recur even after one of these historical filters passed.",
            ""]
    return "\n".join(out)


def build(out=OUT, report=REPORT):
    result = evaluate(load())
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    r = Path(report)
    r.parent.mkdir(parents=True, exist_ok=True)
    r.write_text(human_report(result), encoding="utf-8")
    compact = {"status": result["status"],
               "source": result["source_snapshot_sha256"],
               "frozen": result["full_period_results"]["frozen"],
               "variants": {name: {
                   "cagr": value["cagr"],
                   "maxdd": value["max_drawdown"],
                   "dd_improvement_pp": value["maxdd_improvement_pp"],
                   "cagr_delta_pp": value["cagr_delta_pp"],
                   "interventions": value["intervention_sessions"]}
                   for name, value in result["full_period_results"].items() if name != "frozen"},
               "gates": result["robustness_gate"]}
    print("VOL60_RAMP_REENTRY_RESEARCH=" + json.dumps(compact, sort_keys=True))
    print(f"OUTPUT_JSON={out} OUTPUT_REPORT={report}")
    return result


if __name__ == "__main__":
    build()

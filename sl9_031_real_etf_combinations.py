"""SL9-031: factorized, pinned real-ETF x risk-overlay backtest for ST only.

Reuses immutable SL9-030 Green CI observed-bar artifact, NEVER synthetic ETF
returns; uses original frozen 8.0 signals with causally delayed features.
No AWS writes, broker activity, portfolio promotion, fresh holdout claims.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
from datetime import date
from pathlib import Path
from statistics import stdev

from observed_etf_four_challengers_batch import (
    _ewma_caps, _stage, simulate as original_frozen
)
from observed_etf_vol60_reentry_audit import _features, _raw_cap
from stocklens.core import TARGET_INVESTED_FRACTION, weights_for_leverage
from stocklens_st_real_3x_research import (
    ETFS, SYMS, FEE, CAPITAL, metrics, validate,
)

SOURCE = Path("research/locked/sl9-030/private/st_real_3x_etfs.json")
SOURCE_REPORT = Path("research/locked/sl9-030/results/st_real_3x_etfs.json")
BASE = Path("docs/portal-history.json")
RESULT = Path("research/results/sl9_031_combinations.json")
REPORT = Path("research/reports/sl9_031_combinations.md")
CURVES = Path("research/results/sl9_031_fixed_curves.csv")

# These exact weights and families were frozen BEFORE looking at combinations.
MIXES = {
    "frozen": {"TQQQ": 1.0},
    "q3_upro25": {"TQQQ": .75, "UPRO": .25},
    "q3_soxl25": {"TQQQ": .75, "SOXL": .25},
    "q3_tecl25": {"TQQQ": .75, "TECL": .25},
    "q3_fas25": {"TQQQ": .75, "FAS": .25},
    "q3_soxl12_tecl12": {"TQQQ": .75, "SOXL": .125, "TECL": .125},
    "q3_upro12_soxl12": {"TQQQ": .75, "UPRO": .125, "SOXL": .125},
}
OVERLAYS = (
    "frozen", "cap2", "cap2_5", "ewma5_shock", "vol60_instant",
    "vol60_ramp5", "staged_up3", "vol60_ramp5_ewma5",
)
LAGS = (0, 1)
SLIPS = (10., 20.)
SPLITS = {
    "2010_2017": ("2010-03-11", "2017-12-29"),
    "2018_2022": ("2018-01-02", "2022-12-30"),
    "2023_2026": ("2023-01-03", "2026-10-27"),
    "covid_2020": ("2020-02-20", "2020-05-29"),
    "bear_2022": ("2022-01-03", "2022-10-31"),
}
CURVE_CASES = (
    ("frozen", "frozen"), ("frozen", "vol60_ramp5"),
    ("q3_soxl25", "frozen"), ("q3_soxl25", "vol60_ramp5"),
    ("q3_soxl12_tecl12", "ewma5_shock"),
)
MIN_SESSIONS = 4000


def load_evidence():
    base = json.loads(BASE.read_text(encoding="utf-8"))
    extra = json.loads(SOURCE.read_text(encoding="utf-8"))
    prior = json.loads(SOURCE_REPORT.read_text(encoding="utf-8"))
    rows, bars = validate(base, extra)
    digest = hashlib.sha256(json.dumps(extra["bars"], sort_keys=True,
                      separators=(",", ":")).encode()).hexdigest()
    if (len(rows) < MIN_SESSIONS or prior.get("kind") != "ST_REAL_3X_ETF_FROZEN_8_COMPARISON"
            or prior.get("status") != "HISTORICAL_REUSED_NO_PROMOTION"
            or prior.get("base_sha256") != base.get("snapshot_sha256")
            or prior.get("additional_real_etf_data_sha256") != digest
            or prior.get("captured_utc") != extra.get("captured_utc")
            or prior.get("period", {}).get("sessions") != len(rows)
            or prior.get("period", {}).get("start") != rows[0]["date"]
            or prior.get("period", {}).get("end") != rows[-1]["date"]
            or prior.get("baseline_nav_parity") is not True
            or prior.get("broker_actions") is not False):
        raise ValueError("PINNED_SL9_030_DATA_OR_BASELINE_MISMATCH")
    if abs(TARGET_INVESTED_FRACTION - .985) > 1e-9:
        raise ValueError("FROZEN_8_INVESTED_FRACTION_CHANGED")
    return base, extra, prior, rows, bars


def exposures(rows, overlay, lag):
    """Daily open i may use frozen decision at i-lag and close features <=i-1-lag."""
    if overlay not in OVERLAYS or lag not in LAGS:
        raise ValueError("UNREGISTERED_OVERLAY_OR_LAG")
    rv20, shocks = _features(rows)
    ewma = _ewma_caps(rows)
    cap_state, prev_desired, prev_target, anchor, elapsed = 3., None, None, 0., 0
    out = []
    for i, row in enumerate(rows):
        j = i - lag
        frozen = float(rows[j]["l"]) if j >= 0 else 0.
        desired = frozen
        if overlay == "cap2":
            desired = min(desired, 2.)
        elif overlay == "cap2_5":
            desired = min(desired, 2.5)
        elif overlay == "staged_up3":
            if prev_desired != desired:
                anchor = prev_target if prev_target is not None else desired
                elapsed = 0
                prev_desired = desired
            elapsed += 1
            desired = _stage(prev_target, desired, elapsed, anchor, "staged_up_3")
        if overlay.startswith("vol60"):
            raw = _raw_cap(rv20, shocks, i - 1 - lag, False)
            if overlay == "vol60_instant":
                cap_state = raw
            elif raw < cap_state:
                cap_state = raw
            elif raw > cap_state:
                cap_state = min(raw, cap_state + .4)
            desired = min(desired, cap_state)
        if overlay in ("ewma5_shock", "vol60_ramp5_ewma5") and j >= 1:
            desired = min(desired, ewma[j - 1])
        if not 0 <= desired <= frozen + 1e-10 or desired > 3.:
            raise ValueError("OVERLAY_EXCEEDED_FROZEN_LEVERAGE")
        if frozen == 0. and desired != 0.:
            raise ValueError("FROZEN_CASH_DEFENSE_BROKEN")
        out.append(desired)
        prev_target = desired
    return out


def target_weights(level, mix):
    if mix not in MIXES:
        raise ValueError("UNREGISTERED_3X_MIX")
    fractions = MIXES[mix]
    if abs(sum(fractions.values()) - 1.) > 1e-10:
        raise ValueError("INVALID_PREDECLARED_MIX")
    w = {s: 0. for s in SYMS}
    if level:
        a, b = weights_for_leverage(level)
        w["QQQ"] = a * TARGET_INVESTED_FRACTION
        for s, part in fractions.items():
            w[s] = b * TARGET_INVESTED_FRACTION * part
    if min(w.values()) < 0 or sum(w.values()) > TARGET_INVESTED_FRACTION + 1e-10:
        raise ValueError("PORTFOLIO_OVERSPENT")
    return w


def run_path(rows, bars, mix, levels, slip):
    if mix not in MIXES or slip not in SLIPS or len(levels) != len(rows):
        raise ValueError("UNREGISTERED_BACKTEST")
    cash, holdings, nav, trades, turnover = CAPITAL, {s: 0 for s in SYMS}, [], 0, 0.
    last = None
    for r, lev in zip(rows, levels):
        d = r["date"]
        prices = {"QQQ": {"open": r["qo"], "close": r["qc"]},
                  "TQQQ": {"open": r["to"], "close": r["tc"]}}
        prices.update({s: bars[s][d] for s in ETFS})
        if last is None or abs(lev - last) > 1e-10:
            weight = target_weights(lev, mix)
            equity = cash + sum(holdings[s] * prices[s]["open"] for s in SYMS)
            want = {s: math.floor(equity * weight[s] / prices[s]["open"]) for s in SYMS}
            for s in SYMS:
                excess = holdings[s] - want[s]
                if excess > 0:
                    gross = excess * prices[s]["open"]
                    cash += gross * (1-slip/10000.) * (1-FEE/10000.)
                    turnover += gross
                    holdings[s] -= excess
                    trades += 1
            for s in SYMS:
                needed = want[s] - holdings[s]
                if needed > 0:
                    unit = prices[s]["open"] * (1+slip/10000.) * (1+FEE/10000.)
                    count = min(needed, math.floor(max(0., cash)/unit))
                    if count > 0:
                        cash -= count * unit
                        turnover += count * prices[s]["open"]
                        holdings[s] += count
                        trades += 1
        value = cash + sum(holdings[s] * prices[s]["close"] for s in SYMS)
        if cash < -1e-6 or not math.isfinite(value) or value <= 0:
            raise ValueError("INVALID_WHOLE_SHARE_LEDGER")
        nav.append(value)
        last = lev
    return {"navs": nav, "trades": trades, "turnover_notional": round(turnover, 2)}


def slice_stats(navs, dates, first, last):
    ids = [i for i,d in enumerate(dates) if first <= d <= last]
    if len(ids) < 25:
        raise ValueError("MISSING_PREDECLARED_ERA")
    a, b = ids[0], ids[-1]
    start_value = CAPITAL if a == 0 else navs[a - 1]
    peak, dd = start_value, 0.
    for i in range(a, b+1):
        peak = max(peak, navs[i])
        dd = min(dd, navs[i]/peak-1)
    years = (date.fromisoformat(dates[b])-date.fromisoformat(dates[a])).days/365.2425
    return {"start": dates[a], "end": dates[b],
            "return": navs[b]/start_value - 1.,
            "cagr": (navs[b]/start_value)**(1/years)-1.,
            "local_maxdd": dd}


def evaluate(base, extra, prior, rows, bars):
    dates = [r["date"] for r in rows]
    levels = {(overlay, lag): exposures(rows, overlay, lag)
              for overlay in OVERLAYS for lag in LAGS}
    frozen_runs = {}
    for lag in LAGS:
        for slip in SLIPS:
            actual = run_path(rows, bars, "frozen", levels["frozen", lag], slip)
            ref = original_frozen(rows, mode="frozen", lag=lag, slippage_bps=slip)
            if len(ref["navs"]) != len(actual["navs"]) or any(
                abs(a-b) > 1e-5 for a, b in zip(actual["navs"], ref["navs"])
            ):
                raise ValueError("FROZEN_DAILY_NAV_PARITY_FAILED")
            frozen_runs[lag, slip] = actual

    fixed_curves = {}
    primary = []
    scenarios = {}
    for mix in MIXES:
        for overlay in OVERLAYS:
            cases = []
            primary_path = None
            for lag in LAGS:
                for slip in SLIPS:
                    path = (frozen_runs[lag, slip] if
                            mix == "frozen" and overlay == "frozen" else
                            run_path(rows, bars, mix, levels[overlay, lag], slip))
                    score = metrics(path["navs"], dates)
                    control = metrics(frozen_runs[lag, slip]["navs"], dates)
                    is_primary = lag == 1 and slip == 10.
                    cagr_delta = 100*(score["cagr"]-control["cagr"])
                    dd_gain = 100*(score["maxdd"]-control["maxdd"])
                    # Price path is previously inspected; screen is continuation, not alpha.
                    screen = cagr_delta >= .5 and dd_gain >= -1.
                    cases.append({"additional_lag": lag, "slippage_bps_side": slip,
                                  "cagr": score["cagr"], "maxdd": score["maxdd"],
                                  "cagr_delta_pp": cagr_delta, "drawdown_gain_pp": dd_gain,
                                  "screen": screen})
                    if is_primary:
                        primary_path = path
                        primary_score = score
                        primary_control = control
            assert primary_path is not None
            eras = {name: slice_stats(primary_path["navs"],dates,start,end)
                    for name,(start,end) in SPLITS.items()}
            cases_passed = sum(x["screen"] for x in cases)
            rec = {"mix": mix, "overlay": overlay, **primary_score,
                   "trades": primary_path["trades"],
                   "turnover_notional": primary_path["turnover_notional"],
                   "delta_cagr_pp": 100*(primary_score["cagr"]-primary_control["cagr"]),
                   "drawdown_gain_pp": 100*(primary_score["maxdd"]-primary_control["maxdd"]),
                   "passes": cases_passed,
                   "continuation_only": (mix,overlay)!=("frozen","frozen") and cases_passed==4,
                   "eras": eras}
            primary.append(rec)
            scenarios[f"{mix}|{overlay}"] = cases
            if (mix,overlay) in CURVE_CASES:
                fixed_curves[(mix,overlay)] = primary_path["navs"]
    if set(fixed_curves) != set(CURVE_CASES):
        raise ValueError("MISSING_FIXED_CURVE")
    report = {
        "schema_version": 1,
        "kind": "SL9_031_ST_REAL_ETF_OVERLAY_COMBINATIONS",
        "status": "HISTORICAL_REUSED_COMBINATIONS_NOT_FORWARD_PAPER",
        "period": {"start": dates[0], "end": dates[-1], "sessions": len(dates)},
        "source_previous_run": 40730235493,
        "source_prior_bars_sha256": prior["additional_real_etf_data_sha256"],
        "base_sha256": base["snapshot_sha256"],
        "source_vendor": extra["vendor"],
        "source_independently_audited": False,
        "frozen_daily_parity_all_stress_cases": True,
        "actual_etf_observations_no_synthetic_prices": True,
        "frozen_8_modified": False, "automatic_promotion": False,
        "broker_actions": False, "aws_st_paper_runs": False,
        "pristine_out_of_sample": False,
        "data_snooping_multiple_tests": len(MIXES)*len(OVERLAYS)-1,
        "execution": "real ETF Yahoo adjusted DAILY OPEN proxy, 2bps fee and 10/20bps slippage/side",
        "primary": "one additional frozen-signal/feature delay session, 10bps/side",
        "instrument_rule": "reallocate TQQQ sleeve by fixed ratios in ANY invested exposure level; no independent ETF signal",
        "overlay_rule": "only already-completed QQQ closes; 0x frozen defense unaltered",
        "qualification": "continuation screen >=0.5pp CAGR and <=1pp drawdown deterioration in all 4 stress cases; NOT approval",
        "mixes": MIXES, "overlays": list(OVERLAYS),
        "case_count": len(MIXES)*len(OVERLAYS),
        "stress_runs": len(MIXES)*len(OVERLAYS)*len(LAGS)*len(SLIPS),
        "results": primary, "stress": scenarios,
        "csv_curves": [f"{m}|{o}" for m,o in CURVE_CASES],
    }
    return report, dates, fixed_curves


def build():
    base, extra, prior, rows, bars = load_evidence()
    report, dates, curves = evaluate(base, extra, prior, rows, bars)
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    CURVES.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(report, sort_keys=True, indent=2)+"\n", encoding="utf-8")
    with CURVES.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date"] + ["|".join(c) for c in CURVE_CASES])
        for i,day in enumerate(dates):
            w.writerow([day] + [round(curves[c][i],2) for c in CURVE_CASES])
    ranking = sorted(report["results"],key=lambda x:x["cagr"],reverse=True)
    baseline = next(x for x in report["results"] if x["mix"]=="frozen" and x["overlay"]=="frozen")
    lines = ["# SL9-031: fixed-factor combinations; historical reused observations", "",
       "Research only. Source: pinned SL9-030 actual Yahoo-adjusted ETF OPEN/CLOSE.",
       "56 fixed arms x four delay/slippage stress cases; no new asset optimization.",
       "No untouched OOS, broker execution, provider cross-audit or ST forward receipts.",
       "Unchanged frozen 8.0 day-by-day NAV parity in all 4 stress cases.", "",
       "| Mix | Overlay | CAGR | MaxDD | ΔCAGR pp | MaxDD benefit pp | Passes/4 |",
       "|---|---|---:|---:|---:|---:|---:|"]
    for x in ranking:
        lines.append(f'| {x["mix"]} | {x["overlay"]} | {x["cagr"]:.2%} | {x["maxdd"]:.2%} | {x["delta_cagr_pp"]:+.2f} | {x["drawdown_gain_pp"]:+.2f} | {x["passes"]}/4 |')
    lines += ["", f'Frozen reference primary: CAGR {baseline["cagr"]:.3%}, MaxDD {baseline["maxdd"]:.3%}.',
       "Winner sorting is purely descriptive and likely multiple-testing biased.",
       "Crisis periods and historical eras are descriptive, not independent holdouts.",
       "All signal and risk caps only see already-completed data. No capital promotion.",
       "Private AWS ST S3 and prospective Paper are separate acceptance gates."]
    REPORT.write_text("\n".join(lines)+"\n", encoding="utf-8")
    winners = [x for x in report["results"] if x["continuation_only"]]
    print("SL9_031_COMPLETE=" + json.dumps({"arms":report["case_count"],
           "stress_runs":report["stress_runs"],"period":report["period"],
           "frozen": {"cagr":baseline["cagr"],"maxdd":baseline["maxdd"]},
           "top_cagr": [{"mix":x["mix"],"overlay":x["overlay"],
                         "cagr":x["cagr"],"maxdd":x["maxdd"],"passes":x["passes"]}
                        for x in ranking[:8]],
           "continuation_count":len(winners), "promotion":False}))
    return report


if __name__ == "__main__":
    build()

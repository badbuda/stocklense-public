"""SL-62: overnight and regular-session StockLens research.

Uses 2010-2026 observed, Yahoo-adjusted DAILY QQQ/TQQQ Open/Close.
These are NOT auction fills or live broker trades. All level decisions in
the frozen snapshot predate the session they trade. Research only.
"""
from __future__ import annotations
import argparse
from datetime import date
import json
import math
from pathlib import Path

from observed_etf_two_question_audit import _metrics, _prices, _run as frozen_run, START_CAPITAL
from tradable_tqqq_execution_comparison import _mark, _rebalance
from stocklens.core import weights_for_leverage, TARGET_INVESTED_FRACTION

SOURCE = Path("research/frozen_sources/observed_qqq_tqqq_ml_20100211_20261009.json")
RESULTS = Path("research/results/SL-62-overnight-intraday.json")
REPORT = Path("research/reports/SL-62-overnight-intraday.md")
SHA256 = "bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129"
FEES = {"gross": (0., 0.), "low_cost": (2., 5.), "modeled": (2., 10.)}
MODES = {
    "frozen": (1., 1., "StockLens"),
    "overnight_stocklens": (0., 1., "StockLens"),
    "intraday_stocklens": (1., 0., "StockLens"),
    "reduce_day20": (.8, 1., "StockLens"),
    "reduce_day50": (.5, 1., "StockLens"),
    "reduce_night20": (1., .8, "StockLens"),
    "reduce_night50": (1., .5, "StockLens"),
    "flat_reduction20": (.8, .8, "StockLens"),
    "qqq_overnight": (0., 1., "QQQ"),
    "qqq_intraday": (1., 0., "QQQ"),
    "tqqq_overnight": (0., 1., "TQQQ"),
    "tqqq_intraday": (1., 0., "TQQQ"),
}
PERIODS = {
    "2010_2017": ("2010-02-11", "2017-12-29"),
    "2018_2022": ("2018-01-02", "2022-12-30"),
    "2023_2026": ("2023-01-03", "2026-10-09"),
}


def load(path=SOURCE):
    src = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = src.get("daily", [])
    if (src.get("evidence") != "REAL_QQQ_TQQQ_ADJUSTED_DAILY_OPEN_EXECUTION_PROXY"
            or src.get("full_lean_broker_parity") is not False
            or src.get("live_trading_authorized") is not False
            or src.get("observed_ohlc_available") is not True
            or src.get("snapshot_sha256") != SHA256):
        raise ValueError("UNTRUSTED_DAILY_SOURCE")
    if len(rows) != 4191 or src.get("period", {}).get("sessions") != len(rows):
        raise ValueError("BAD_COHORT_SIZE")
    if rows[0]["date"] != "2010-02-11" or rows[-1]["date"] != "2026-10-09":
        raise ValueError("WRONG_COHORT_BOUNDARIES")
    prev = ""
    for row in rows:
        d = row["date"]
        date.fromisoformat(d)
        if (d <= prev or row.get("signal", "") >= d
                or row.get("l") not in (0, 1.25, 2., 3.)
                or row.get("contribution") != 0):
            raise ValueError("LOOKAHEAD_OR_FROZEN_SIGNAL_FAILURE")
        if not all(isinstance(row.get(k), (int, float)) and
                   math.isfinite(row[k]) and row[k] > 0
                   for k in ("qo", "qc", "to", "tc")):
            raise ValueError("BAD_OBSERVED_PRICE")
        prev = d
    return src


def target(level, fraction, asset):
    if not 0 <= fraction <= 1:
        raise ValueError("BAD_FRACTION")
    if asset == "QQQ":
        return {"QQQ": .985 * fraction, "TQQQ": 0.}
    if asset == "TQQQ":
        return {"QQQ": 0., "TQQQ": .985 * fraction}
    if asset != "StockLens":
        raise ValueError("BAD_ASSET")
    if not level:
        return {"QQQ": 0., "TQQQ": 0.}
    q, t = weights_for_leverage(level)
    return {"QQQ": TARGET_INVESTED_FRACTION * q * fraction,
            "TQQQ": TARGET_INVESTED_FRACTION * t * fraction}


def replay(rows, *, day_fraction=1., night_fraction=1., asset="StockLens",
           fee=2., slip=10.):
    """Day exposure: OPEN->CLOSE; night: CLOSE->next OPEN.

    The close trade references the PRIOR-session frozen l, NOT same-close data.
    Overnight holds include nontrading calendar gaps. Whole-share, cash-constrained.
    """
    if fee < 0 or slip < 0:
        raise ValueError("NEGATIVE_FRICTION")
    p = {"cash": START_CAPITAL, "shares": {"QQQ": 0, "TQQQ": 0},
         "fees": 0., "slippage": 0., "trades": 0, "turnover_notional": 0.}
    navs, prior = [], None
    for r in rows:
        level = r["l"] if asset == "StockLens" else (1. if asset == "QQQ" else 3.)
        prices = _prices(r)
        if prior is None or level != prior or day_fraction != night_fraction:
            _rebalance(p, prices, target(level, day_fraction, asset), fee, slip)
        if day_fraction != night_fraction:
            # The imported model trades at the field named open. Feed the
            # completed session's close as that field for the close action.
            close_prices = {s: {"open": prices[s]["close"],
                                 "close": prices[s]["close"]}
                            for s in ("QQQ", "TQQQ")}
            _rebalance(p, close_prices, target(level, night_fraction, asset),
                       fee, slip)
        nav = _mark(p, prices, "close")
        if not math.isfinite(nav) or nav <= 0 or p["cash"] < -1e-5:
            raise ValueError("BAD_ACCOUNT")
        navs.append(nav)
        prior = level
    stats = _metrics(navs, [r["date"] for r in rows])
    for name, (first, last) in PERIODS.items():
        indices = [i for i, r in enumerate(rows) if first <= r["date"] <= last]
        if indices:
            a, b = indices[0], indices[-1]
            basis = START_CAPITAL if a == 0 else navs[a - 1]
            stats["return_" + name] = navs[b] / basis - 1.
    return {**stats, "orders": p["trades"], "modeled_fees": p["fees"],
            "modeled_slippage": p["slippage"],
            "turnover_notional": p["turnover_notional"], "navs": navs}


def evaluate(src):
    rows = src["daily"]
    baseline = frozen_run(rows, variant="frozen")
    result = {}
    for name, (day, night, asset) in MODES.items():
        result[name] = {}
        for cost, (fee, slip) in FEES.items():
            x = replay(rows, day_fraction=day, night_fraction=night,
                       asset=asset, fee=fee, slip=slip)
            if name == "frozen" and cost == "modeled":
                if len(x["navs"]) != len(baseline["navs"]) or any(
                    abs(a - b) / b > 2e-10 for a, b in zip(x["navs"], baseline["navs"])
                ):
                    raise ValueError("FROZEN_NAV_PARITY_FAILURE")
            del x["navs"]
            result[name][cost] = x
    return {"experiment": "SL-62", "status": "RETROSPECTIVE_DAILY_PROXY_ONLY",
            "period": src["period"], "source_sha256": src["snapshot_sha256"],
            "costs_bps_per_side": FEES, "no_lookahead": True,
            "tax_model": "NOT_INCLUDED", "minute_auction_prices": "NOT_AVAILABLE",
            "prod_unchanged": True, "broker_orders_allowed": False,
            "no_clean_holdout": True, "results": result}


def report(data):
    fmt = lambda x: f"{100 * x:.2f}%"
    lines = [
        "# SL-62: Overnight / intraday ON TOP of StockLens 8.0",
        "",
        "Retrospective Yahoo-adjusted DAILY Open/Close proxy only; not actual MOO/MOC fills.",
        "Period: 2010-02-11 to 2026-10-09; 4,191 sessions, $100,000 inception.",
        "Fixed prior-session frozen exposure; no same-close lookahead, no contributions.",
        "",
        "| Mode | Gross CAGR | Modeled CAGR | Modeled MaxDD | Orders |",
        "|---|---:|---:|---:|---:|",
    ]
    for name, z in data["results"].items():
        gross, model = z["gross"], z["modeled"]
        lines.append(f"| {name} | {fmt(gross['cagr'])} | "
                     f"{fmt(model['cagr'])} | {fmt(model['max_drawdown'])} | "
                     f"{model['orders']:,} |")
    lines += [
        "",
        "Fees: modeled 2 bps + 10 bps slippage per side; lower-cost stress 2+5 bps.",
        "Close trades use ONLY the already-frozen prior-session risk level.",
        "Percent exposures mask the same 0-3x frozen exposure and DO NOT add leverage.",
        "Zero-cost is impossible to implement literally; these are historical diagnostics.",
        "Daily trading creates many taxable sales. No Israeli realized tax/FX lots, broker",
        "minimums, MOC/MOO auction or 09:31 quotes, missed fills or independent vendor parity.",
        "No strategy promotion. No AWS/production/paper or broker mutations.",
        "Validate minute execution, actual fees, tax and untouched prospective OOS before use.",
        "",
    ]
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", type=Path, default=SOURCE)
    ap.add_argument("--out", type=Path, default=RESULTS)
    ap.add_argument("--report", type=Path, default=REPORT)
    opts = ap.parse_args()
    result = evaluate(load(opts.source))
    opts.out.parent.mkdir(parents=True, exist_ok=True)
    opts.report.parent.mkdir(parents=True, exist_ok=True)
    opts.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    opts.report.write_text(report(result) + "\n", encoding="utf-8")
    print(json.dumps({"experiment": "SL-62", "status": result["status"],
                      "result": str(opts.out), "report": str(opts.report)}))


if __name__ == "__main__":
    main()

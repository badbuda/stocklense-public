"""Exploratory StockLens 8.0 + TQQQ/SQQQ video overlays (research-only).

Daily observed QQQ/TQQQ prices; SQQQ 30-minute rule is deliberately NOT
backtested because this frozen snapshot contains no intraday/SQQQ bars.
All historical periods have been repeatedly reused, so no OOS claim.
"""
from __future__ import annotations
import json
import math
from datetime import date
from pathlib import Path

DATA = Path(__file__).resolve().parent / "frozen_sources" / "observed_qqq_tqqq_ml_20100211_20261009.json"
OUTPUT = Path(__file__).resolve().parent / "results" / "video_tqqq_sqqq_overlays_20261110.json"
SOURCE_SHA = "bd2e53c6bbaa4d47247cc0b9c80094c268bb8354c1873c53901030f4b4011129"
MODES = (
    "frozen", "50_half_premium", "50_cap_125", "20x50_cap_125",
    "both_50_20x50", "50_no_upshift",
    "80_core_20_cash", "80_core_20_tqqq_hold",
    "80_core_20_swing_no_filter", "80_core_20_swing_sma50",
    "80_core_20_swing_both", "80_core_20_swing_50pluscorecap",
)
CAPITAL = 100_000.0
FEE_BPS = 2.0
SLEEVE_FRACTION = .2
LAGS = (0, 1)
SLIPPAGES = (10.0, 20.0)


def load():
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    rows = raw["daily"]
    if (raw["snapshot_sha256"] != SOURCE_SHA
            or raw["period"] != {"start": "2010-02-11", "end": "2026-10-09", "sessions": 4191}
            or len(rows) != 4191
            or raw.get("instruments") != ["QQQ", "TQQQ"]
            or raw.get("observed_ohlc_available") is not True):
        raise ValueError("SOURCE_FROZEN_ETF_CONTRACT_FAILED")
    if [r["date"] for r in rows] != sorted({r["date"] for r in rows}):
        raise ValueError("DATE_ORDER_OR_DUPLICATES")
    for row in rows:
        if row["signal"] >= row["date"] or row["l"] not in (0, 1.25, 2, 3):
            raise ValueError("LOOKAHEAD_OR_INVALID_STOCKLENS_SIGNAL")
        if any(not isinstance(row.get(k), (float, int)) or not math.isfinite(row[k])
               or row[k] <= 0 for k in ("qo", "qc", "to", "tc")):
            raise ValueError("INVALID_OBSERVED_DAILY_BAR")
    return raw


def moving_average(closes, window):
    result, total = [], 0.0
    for i, close in enumerate(closes):
        total += close
        if i >= window:
            total -= closes[i - window]
        result.append(total / window if i >= window - 1 else None)
    return result


def feature_rows(rows):
    closes = [float(r["qc"]) for r in rows]
    return closes, moving_average(closes, 20), moving_average(closes, 50)


def leverage_for(mode, rows, i, lag, closes, sma20, sma50, previous):
    """At open i, source level is already based on <= close i-1.
    Additional lag shifts source and feature observation back in lockstep.
    """
    j, k = i - lag, i - 1 - lag
    leverage = float(rows[j]["l"]) if j >= 0 else 0.0
    if k < 49 or leverage <= 0:
        return leverage
    below50 = closes[k] < sma50[k]
    bearcross = sma20[k] < sma50[k]
    if mode == "50_half_premium" and below50:
        return 1.0 + (leverage - 1.0) / 2.0
    if mode == "50_cap_125" and below50:
        return min(leverage, 1.25)
    if mode == "20x50_cap_125" and bearcross:
        return min(leverage, 1.25)
    if mode == "both_50_20x50":
        if below50 and bearcross:
            return min(leverage, 1.25)
        if below50 or bearcross:
            return min(leverage, 2.0)
    if mode == "50_no_upshift" and below50 and previous is not None:
        return min(leverage, previous)
    if mode == "80_core_20_swing_50pluscorecap" and below50:
        return 1.0 + (leverage - 1.0) / 2.0
    return leverage


def weights(leverage):
    if leverage == 0:
        return (0.0, 0.0)
    tqqq = (leverage - 1.0) / 2.0
    return (.985 * (1.0 - tqqq), .985 * tqqq)


def rebalance(core, opens, leverage, slippage):
    eq = core["cash"] + sum(sh * price for sh, price in zip(core["shares"], opens))
    target = [math.floor(eq * w / price) for w, price in zip(weights(leverage), opens)]
    for k in range(2):
        qty = core["shares"][k] - target[k]
        if qty > 0:
            core["cash"] += qty * opens[k] * (1 - slippage / 10000) * (1 - FEE_BPS / 10000)
            core["shares"][k] -= qty
            core["trades"] += 1
    for k in range(2):
        qty = target[k] - core["shares"][k]
        if qty > 0:
            unit = opens[k] * (1 + slippage / 10000) * (1 + FEE_BPS / 10000)
            filled = min(qty, math.floor(max(0.0, core["cash"]) / unit))
            if filled:
                core["cash"] -= filled * unit
                core["shares"][k] += filled
                core["trades"] += 1
    if core["cash"] < -1e-5:
        raise ValueError("CASH_NEGATIVE_AFTER_REBALANCE")


def metric(navs, dates, trades):
    first, last = CAPITAL, navs[-1]
    yrs = (date.fromisoformat(dates[-1]) - date.fromisoformat(dates[0])).days / 365.2425
    peak, dd, old = first, 0.0, first
    returns = []
    for value in navs:
        peak = max(peak, value)
        dd = min(dd, value / peak - 1.0)
        returns.append(value / old - 1.0)
        old = value
    avg = sum(returns) / len(returns)
    sigma = math.sqrt(sum((ret - avg)**2 for ret in returns) / (len(returns) - 1))
    return {
        "cagr": (last / first)**(1.0 / yrs) - 1.0,
        "maxdd": dd, "sharpe_zero_rf": avg * math.sqrt(252) / sigma,
        "ending_equity": last, "trades": trades,
    }


def replay(rows, mode, lag=1, slippage=10.0):
    if mode not in MODES or lag not in LAGS or slippage not in SLIPPAGES:
        raise ValueError("UNREGISTERED_EXPLORATORY_CONFIG")
    closes, ma20, ma50 = feature_rows(rows)
    is_sleeve = mode.startswith("80_core_")
    cash_core = CAPITAL * (1 - SLEEVE_FRACTION) if is_sleeve else CAPITAL
    core = {"cash": cash_core, "shares": [0, 0], "trades": 0}
    sleeve = {"cash": CAPITAL - cash_core, "lots": [], "trades": 0}
    navs, prev, round_trips, wins = [], None, 0, 0
    for i, row in enumerate(rows):
        opens, ends = (row["qo"], row["to"]), (row["qc"], row["tc"])
        lev = leverage_for(mode, rows, i, lag, closes, ma20, ma50, prev)
        if prev is None or abs(lev - prev) > 1e-9:
            rebalance(core, opens, lev, slippage)
        prev = lev
        if mode == "80_core_20_tqqq_hold" and i == 0:
            unit = row["to"] * (1 + slippage / 10000) * (1 + FEE_BPS / 10000)
            wanted = math.floor(.985 * sleeve["cash"] / row["to"])
            qty = min(wanted, math.floor(sleeve["cash"] / unit))
            if qty:
                sleeve["cash"] -= qty * unit
                sleeve["lots"].append({"qty": qty, "buy": i,
                                       "entry": row["to"] * (1 + slippage / 10000), "cost": qty * unit})
                sleeve["trades"] += 1
        if mode.startswith("80_core_20_swing_"):
            k = i - 1 - lag
            kept = []
            for lot in sleeve["lots"]:
                age = i - lot["buy"]
                # Profit information is from the PREVIOUS completed bar.
                # We exit only at NEXT session's OPEN; never assume an intraday limit fill.
                gained = i > 0 and age >= 3 and rows[i-1]["tc"] / lot["entry"] - 1 >= .005
                if age >= 5 or gained:
                    proceeds = lot["qty"] * row["to"] * (1 - slippage / 10000) * (1 - FEE_BPS / 10000)
                    sleeve["cash"] += proceeds
                    wins += int(proceeds >= lot["cost"])
                    round_trips += 1
                    sleeve["trades"] += 1
                else:
                    kept.append(lot)
            sleeve["lots"] = kept
            k = i - 1 - lag
            ready = k >= 49
            if ready:
                below50 = closes[k] < ma50[k]
                bearish = ma20[k] < ma50[k]
                ready = (mode == "80_core_20_swing_no_filter"
                         or mode in ("80_core_20_swing_sma50", "80_core_20_swing_50pluscorecap") and not below50
                         or mode == "80_core_20_swing_both" and not below50 and not bearish)
            if ready and len(sleeve["lots"]) < 5:
                equity = sleeve["cash"] + sum(lot["qty"] * row["to"] for lot in sleeve["lots"])
                unit = row["to"] * (1 + slippage / 10000) * (1 + FEE_BPS / 10000)
                qty = math.floor(min(equity * .1, sleeve["cash"]) / unit)
                if qty > 0:
                    sleeve["cash"] -= qty * unit
                    sleeve["lots"].append({"qty": qty, "buy": i,
                                           "entry": row["to"] * (1 + slippage / 10000), "cost": qty * unit})
                    sleeve["trades"] += 1
        nav = (core["cash"] + sum(sh * price for sh, price in zip(core["shares"], ends))
               + sleeve["cash"] + sum(lot["qty"] * row["tc"] for lot in sleeve["lots"]))
        if not math.isfinite(nav) or nav <= 0 or min(core["cash"], sleeve["cash"]) < -1e-5:
            raise ValueError("ACCOUNT_INVALID")
        navs.append(nav)
    result = metric(navs, [r["date"] for r in rows], core["trades"] + sleeve["trades"])
    result.update({"round_trips": round_trips, "winning_round_trips": wins,
                   "win_rate": wins / round_trips if round_trips else None,
                   "sleeve_trades": sleeve["trades"], "navs": navs})
    return result


def evaluate(raw):
    rows = raw["daily"]
    reference = replay(rows, "frozen", 0, 10.0)
    expected = raw["without_contributions"]["strategy"]
    if (abs(reference["ending_equity"] - expected["ending_equity"]) > .001
            or reference["trades"] != expected["trades"]):
        raise ValueError("FROZEN_DAILY_REFERENCE_PARITY_FAILED")
    cases = {}
    for mode in MODES:
        cases[mode] = {}
        for lag in LAGS:
            for slip in SLIPPAGES:
                r = replay(rows, mode, lag, slip)
                r.pop("navs")
                cases[mode][f"lag{lag}_slip{int(slip)}"] = r
    base = cases["frozen"]["lag1_slip10"]
    summary = []
    for mode in MODES:
        r = cases[mode]["lag1_slip10"]
        summary.append({
            "mode": mode, **r,
            "delta_cagr_pp": 100 * (r["cagr"] - base["cagr"]),
            "maxdd_gain_pp": 100 * (r["maxdd"] - base["maxdd"]),
        })
    return {
        "kind": "EXPLORATORY_TQQQ_SQQQ_VIDEO_STOCKLENS_OVERLAYS",
        "source_snapshot_sha256": SOURCE_SHA,
        "period": raw["period"], "frozen_reference_parity": True,
        "primary": "lag1_slip10", "fee_bps_per_side": FEE_BPS,
        "execution": "observed adjusted daily OPEN (not 30min/intraday)",
        "swing": {"allocation": "80pct frozen 8.0 core + 20pct separately funded sleeve",
                  "new_lot": "10pct of current sleeve equity per eligible trading OPEN",
                  "exit": "minimum 3 sessions, exit on next OPEN after prior-close +0.5pct or age 5",
                  "limit_orders_modeled": False},
        "intraday_sqqq_backtest": "BLOCKED_MISSING_INTRADAY_QQQ_AND_SQQQ_BARS",
        "is_clean_oos": False, "after_tax": False, "broker_fills": False,
        "frozen_strategy_modified": False, "production_writes": False,
        "promotion_authorized": False,
        "primary_summary": summary, "stress": cases,
    }


def main():
    result = evaluate(load())
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print("VIDEO_OVERLAY_FROZEN_PARITY=" + str(result["frozen_reference_parity"]))
    for row in result["primary_summary"]:
        print(f'{row["mode"]:34s} CAGR={row["cagr"]:.2%} DD={row["maxdd"]:.2%} '
              f'dCAGR={row["delta_cagr_pp"]:+.2f}pp dDD={row["maxdd_gain_pp"]:+.2f}pp '
              f'trades={row["trades"]}')
    print("VIDEO_SQQQ_INTRADAY=BLOCKED_MISSING_MINUTE_DATA")
    print("VIDEO_OVERLAY_PROMOTION=FALSE")


if __name__ == "__main__":
    main()

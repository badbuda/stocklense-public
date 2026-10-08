"""Observed QQQ/TQQQ execution-proxy stress test (not original LEAN or broker fills).

The frozen StockLens decisions are computed from QQQ completed closes. Orders are
modeled at the following session's adjusted daily OPEN, never that same close.
Adjusted open is a daily proxy; historical 09:31/09:32 fills are unavailable.
"""
from __future__ import annotations

import hashlib
import json
import math
from datetime import date
from pathlib import Path

from stocklens.core import (
    TARGET_INVESTED_FRACTION,
    replay_levels,
    weights_for_leverage,
)
from stocklens.data import _drop_incomplete_current_session

START = "2010-02-09"
INITIAL_CAPITAL = 100_000.0
MONTHLY_CONTRIBUTION = 3_500.0
REPORT_PATH = "research/tradable_tqqq_execution_comparison.json"
PUBLIC_PATH = "docs/tradable_tqqq_execution_comparison.json"


def _download(symbol: str) -> dict[str, dict[str, float]]:
    import pandas as pd
    import yfinance as yf

    raw = yf.download(
        symbol, start="2008-01-01" if symbol == "QQQ" else START,
        interval="1d", auto_adjust=True, progress=False, actions=False,
        threads=False,
    )
    if raw is None or raw.empty:
        raise RuntimeError("MISSING_OBSERVED_" + symbol)
    if isinstance(raw.columns, pd.MultiIndex):
        open_series, close_series = raw["Open"][symbol], raw["Close"][symbol]
    else:
        open_series, close_series = raw["Open"], raw["Close"]
    df = pd.DataFrame({
        "Date": pd.to_datetime(open_series.index),
        "Open": pd.to_numeric(open_series.values, errors="coerce"),
        "Close": pd.to_numeric(close_series.values, errors="coerce"),
    })
    df = df.dropna().drop_duplicates("Date").sort_values("Date")
    df = df[(df.Open > 0) & (df.Close > 0)]
    if df.empty:
        raise RuntimeError("INVALID_OBSERVED_" + symbol)
    completed, audit = _drop_incomplete_current_session(df)
    if completed.empty:
        raise RuntimeError("NO_COMPLETED_" + symbol)
    result = {
        x.Date.date().isoformat(): {"open": float(x.Open), "close": float(x.Close)}
        for x in completed.itertuples(index=False)
    }
    if not result or not all(
        math.isfinite(y) and y > 0
        for row in result.values() for y in row.values()
    ):
        raise RuntimeError("BAD_PRICES_" + symbol)
    return result


def _validate_prices(qqq: dict, tqqq: dict) -> list[str]:
    dates = sorted(qqq)
    if len(dates) < 3000 or dates[0] > "2008-01-10":
        raise ValueError("INSUFFICIENT_QQQ_WARMUP")
    if not tqqq or min(tqqq) > "2010-02-12":
        raise ValueError("TQQQ_INCEPTION_UNVERIFIED")
    start = max(START, min(tqqq))
    cohort = [d for d in dates if d >= start]
    if len(cohort) < 3000 or cohort[-1] != max(tqqq):
        raise ValueError("NO_CURRENT_MATCHED_COHORT")
    if any(d not in tqqq for d in cohort):
        raise ValueError("MISSING_TQQQ_TRADING_SESSIONS")
    for source in (qqq, tqqq):
        for d, prices in source.items():
            if not all(math.isfinite(float(prices[key])) and float(prices[key]) > 0
                       for key in ("open", "close")):
                raise ValueError("NONPOSITIVE_OR_NONFINITE_PRICE:" + d)
    return cohort


def _trade(portfolio: dict, symbol: str, side: str, quantity: int,
           reference: float, fee_bps: float, slippage_bps: float) -> None:
    if quantity <= 0:
        return
    fill = reference * (1 + slippage_bps / 10000.0 * (1 if side == "BUY" else -1))
    notional = quantity * fill
    commission = notional * fee_bps / 10000.0
    if side == "BUY":
        if portfolio["cash"] + 1e-7 < notional + commission:
            raise ValueError("NEGATIVE_CASH_EXECUTION")
        portfolio["cash"] -= notional + commission
        portfolio["shares"][symbol] += quantity
    else:
        if portfolio["shares"][symbol] < quantity:
            raise ValueError("SHORT_SALE_NOT_ALLOWED")
        portfolio["cash"] += notional - commission
        portfolio["shares"][symbol] -= quantity
    portfolio["fees"] += commission
    portfolio["slippage"] += abs(fill - reference) * quantity
    portfolio["trades"] += 1
    portfolio["turnover_notional"] += reference * quantity


def _mark(p: dict, prices: dict, field: str) -> float:
    return p["cash"] + sum(p["shares"][symbol] * prices[symbol][field]
                           for symbol in ("QQQ", "TQQQ"))


def _rebalance(p: dict, prices: dict, target: dict, fee_bps: float,
               slippage_bps: float) -> None:
    equity = _mark(p, prices, "open")
    targets = {
        symbol: math.floor(equity * target.get(symbol, 0.0) /
                           prices[symbol]["open"])
        for symbol in ("QQQ", "TQQQ")
    }
    for symbol in ("QQQ", "TQQQ"):
        excess = p["shares"][symbol] - targets[symbol]
        if excess > 0:
            _trade(p, symbol, "SELL", excess, prices[symbol]["open"],
                   fee_bps, slippage_bps)
    for symbol in ("QQQ", "TQQQ"):
        missing = targets[symbol] - p["shares"][symbol]
        if missing > 0:
            reference = prices[symbol]["open"]
            filled = reference * (1 + slippage_bps / 10000.0)
            limit = math.floor(max(0.0, p["cash"]) /
                               (filled * (1 + fee_bps / 10000.0)))
            _trade(p, symbol, "BUY", min(missing, limit), reference,
                   fee_bps, slippage_bps)
    if p["cash"] < -1e-6:
        raise ValueError("NEGATIVE_CASH_AFTER_REBALANCE")


def run_execution(qqq: dict, tqqq: dict, decisions: dict, *,
                  monthly: float = 0.0, extra_signal_lag: int = 0,
                  fee_bps: float = 2.0, slippage_bps: float = 10.0,
                  initial: float = INITIAL_CAPITAL) -> dict:
    """Compare two independently executed, whole-share portfolios on identical dates."""
    if any(not math.isfinite(float(v)) or float(v) < 0 for v in
           (monthly, extra_signal_lag, fee_bps, slippage_bps)) or initial <= 0:
        raise ValueError("INVALID_EXECUTION_ASSUMPTIONS")
    if int(extra_signal_lag) != extra_signal_lag:
        raise ValueError("NONINTEGER_DECISION_LAG")
    cohort = _validate_prices(qqq, tqqq)
    full_days = sorted(qqq)
    day_to_index = {d: i for i, d in enumerate(full_days)}
    strategies = {
        "stocklens": {"cash": float(initial), "shares": {"QQQ": 0, "TQQQ": 0},
                      "fees": 0.0, "slippage": 0.0, "trades": 0, "turnover_notional": 0.0},
        "qqq": {"cash": float(initial), "shares": {"QQQ": 0, "TQQQ": 0},
                "fees": 0.0, "slippage": 0.0, "trades": 0, "turnover_notional": 0.0},
    }
    peak = {key: float(initial) for key in strategies}
    maxdd = {key: 0.0 for key in strategies}
    paid = float(initial)
    last_month, last_leverage = None, None
    recent = []
    events = []
    for d in cohort:
        i = day_to_index[d]
        signal_index = i - 1 - int(extra_signal_lag)
        if signal_index < 0:
            raise ValueError("DECISION_NOT_PREVIOUSLY_AVAILABLE")
        signal_date = full_days[signal_index]
        if signal_date not in decisions:
            raise ValueError("MISSING_PRIOR_COMPLETED_CLOSE_SIGNAL:" + signal_date)
        lev = float(decisions[signal_date])
        if lev not in (0.0, 1.25, 2.0, 3.0):
            raise ValueError("FROZEN_EXPOSURE_NOT_RECOGNIZED")
        wqqq, wtqqq = weights_for_leverage(lev)
        weights = {"QQQ": wqqq * TARGET_INVESTED_FRACTION,
                   "TQQQ": wtqqq * TARGET_INVESTED_FRACTION}
        if lev == 0.0:
            weights = {"QQQ": 0.0, "TQQQ": 0.0}
        if sum(weights.values()) > 1.000000001:
            raise ValueError("LEVERAGE_IMPLIES_BORROWING")
        deposit = float(monthly) if last_month is not None and d[:7] != last_month else 0.0
        paid += deposit
        prices = {"QQQ": qqq[d], "TQQQ": tqqq[d]}
        for p in strategies.values():
            p["cash"] += deposit
        should_rebalance = last_leverage is None or lev != last_leverage or deposit > 0
        if should_rebalance:
            _rebalance(strategies["stocklens"], prices, weights, fee_bps, slippage_bps)
        if last_month is None or deposit > 0:
            _rebalance(strategies["qqq"], prices, {"QQQ": 1.0, "TQQQ": 0.0},
                       fee_bps, slippage_bps)
        record = {"date": d, "effective_prior_signal_date": signal_date,
                  "leverage": lev, "contribution": deposit,
                  "rebalance": should_rebalance}
        for name, p in strategies.items():
            net = _mark(p, prices, "close")
            if not math.isfinite(net) or net <= 0:
                raise ValueError("NONPOSITIVE_PORTFOLIO_NAV")
            peak[name] = max(peak[name], net)
            maxdd[name] = min(maxdd[name], net / peak[name] - 1.0)
            record[name + "_nav"] = round(net, 6)
        recent.append(record)
        if should_rebalance:
            events.append({"date": d, "signal_date": signal_date,
                           "target_leverage": lev, "monthly_deposit": deposit})
        last_leverage, last_month = lev, d[:7]
    years = (date.fromisoformat(cohort[-1]) - date.fromisoformat(cohort[0])).days / 365.2425
    def stats(name: str) -> dict:
        p = strategies[name]
        last = recent[-1][name + "_nav"]
        return {
            "ending_equity": last,
            "paid_capital": paid,
            "profit_loss": last - paid,
            "cagr_without_contributions": (last / initial) ** (1 / years) - 1
            if monthly == 0 else None,
            "max_drawdown": maxdd[name],
            "total_modeled_commissions": p["fees"],
            "total_modeled_slippage": p["slippage"],
            "trades": p["trades"],
            "turnover_notional": p["turnover_notional"],
            "ending_cash": p["cash"],
            "ending_shares": p["shares"],
        }
    return {
        "start": cohort[0], "end": cohort[-1], "sessions": len(cohort),
        "additional_signal_lag_sessions": int(extra_signal_lag),
        "monthly_contribution": monthly, "fee_bps_per_side": fee_bps,
        "slippage_bps_per_side": slippage_bps,
        "stocklens": stats("stocklens"), "qqq_buy_hold": stats("qqq"),
        "ending_equity_ratio": stats("stocklens")["ending_equity"] /
                               stats("qqq")["ending_equity"],
        "ending_equity_delta": stats("stocklens")["ending_equity"] -
                               stats("qqq")["ending_equity"],
        "events": events[-12:],
        "chart_rows": recent[::21] + ([recent[-1]] if recent[-1] != recent[::21][-1] else []),
    }


def build(out: str = REPORT_PATH, public_out: str = PUBLIC_PATH) -> dict:
    qqq = _download("QQQ")
    tqqq = _download("TQQQ")
    dates = sorted(qqq)
    decisions = {
        d.asof_date: float(d.target_leverage)
        for d in replay_levels([qqq[d]["close"] for d in dates], dates)
    }
    evidence = "\n".join(f"{d},{qqq[d]['open']:.12g},{qqq[d]['close']:.12g},"
                         f"{tqqq[d]['open']:.12g},{tqqq[d]['close']:.12g}"
                         for d in sorted(tqqq) if d in qqq)
    digest = hashlib.sha256(evidence.encode()).hexdigest()
    no_contrib = run_execution(qqq, tqqq, decisions)
    monthly = run_execution(qqq, tqqq, decisions, monthly=MONTHLY_CONTRIBUTION)
    cost_grid = [
        {"slippage_bps_per_side": b,
         **{k: v for k, v in run_execution(qqq, tqqq, decisions,
                 slippage_bps=b).items()
            if k in ("stocklens", "qqq_buy_hold", "ending_equity_ratio")}}
        for b in (0.0, 5.0, 10.0, 25.0, 50.0)
    ]
    delay_grid = [
        {"additional_signal_lag_sessions": d,
         **{k: v for k, v in run_execution(qqq, tqqq, decisions,
                 extra_signal_lag=d).items()
            if k in ("stocklens", "qqq_buy_hold", "ending_equity_ratio")}}
        for d in (0, 1, 2)
    ]
    data = {
        "schema_version": 1,
        "status": "PASS",
        "kind": "OBSERVED_QQQ_TQQQ_DAILY_OPEN_EXECUTION_PROXY",
        "baseline": "StockLens 8.0 FROZEN",
        "price_source": "YFINANCE_AUTO_ADJUSTED_DAILY_OPEN_AND_CLOSE",
        "observed_instruments": ["QQQ", "TQQQ"],
        "price_fingerprint_sha256": digest,
        "first_valid_real_TQQQ_date": min(tqqq),
        "period": {"start": no_contrib["start"], "end": no_contrib["end"],
                   "sessions": no_contrib["sessions"]},
        "signal_policy": "Only the most recent completed QQQ close available BEFORE the execution session.",
        "execution_policy": "Next-session adjusted daily OPEN proxy for all buys and sells; sell first, then buy. Rebalance on level change or contribution, whole shares and available cash only. No same-session close lookahead.",
        "instrument_weights": "Frozen 8.0 target: level 1.25 = 86.1875% QQQ + 12.3125% TQQQ + 1.5% cash; level 2 = 49.25% each + 1.5% cash; level 3 = 98.5% TQQQ + 1.5% cash; level 0 = cash.",
        "commissions_bps_each_side": 2,
        "slippage_bps_each_side": 10,
        "no_contributions": no_contrib,
        "initial_100k_monthly_3500": monthly,
        "slippage_stress_no_contributions": cost_grid,
        "signal_lag_stress_no_contributions": delay_grid,
        "evidence_class": "TRADEABLE_ETF_HISTORICAL_PRICE_EXECUTION_PROXY",
        "full_lean_execution_parity": False,
        "broker_fills_observed": False,
        "intraday_0931_0932_fills_observed": False,
        "automatic_trading_authorized": False,
        "automatic_model_promotion": False,
        "limitations": [
            "Daily OPEN is not the frozen 09:31 reductions / 09:32 additions timestamp. No historical minute-bar fill data is claimed.",
            "Adjusted OHLC approximates distributions and splits; trades use adjustment-normalized prices, not historical raw brokerage executions.",
            "Yahoo prices are not original LEAN same-input parity.",
            "Share-level execution is whole-share and cash-constrained; estimated commission and slippage are assumptions, not observed fills.",
            "Starts at real TQQQ inception in 2010, not 2009. QQQ benchmark is matched on identical dates, starting equity and contributions.",
            "Frozen model decisions may have been selected using past sample results; historical outperformance is not out-of-sample proof.",
        ],
    }
    for output in (out, public_out):
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                        encoding="utf-8")
    return data


if __name__ == "__main__":
    report = build()
    print(json.dumps({
        "status": report["status"],
        "period": report["period"],
        "no_contributions": {
            "stocklens": report["no_contributions"]["stocklens"],
            "qqq": report["no_contributions"]["qqq_buy_hold"],
            "relative_ratio": report["no_contributions"]["ending_equity_ratio"],
        },
        "monthly_contributions": {
            "stocklens": report["initial_100k_monthly_3500"]["stocklens"]["ending_equity"],
            "qqq": report["initial_100k_monthly_3500"]["qqq_buy_hold"]["ending_equity"],
        },
        "evidence_class": report["evidence_class"],
    }, indent=2))

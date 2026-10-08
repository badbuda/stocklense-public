from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
import math
import time as _time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

NY_TZ = ZoneInfo("America/New_York")
SYMBOLS = ("QQQ", "TQQQ")
PAPER_INITIAL_EQUITY = 100_000.0
FEE_BPS = 2.0
SLIPPAGE_BPS = 10.0


@dataclass(frozen=True)
class SessionMarket:
    session_date: str
    prices_0931: dict[str, float]
    prices_0932: dict[str, float]
    closes: dict[str, float]
    dividends: dict[str, float]
    split_ratios: dict[str, float]
    source: str = "YFINANCE_1M_RAW"


class PaperIntegrityError(RuntimeError):
    pass


def _positive(x: Any) -> bool:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return False
    return math.isfinite(v) and v > 0


def _normalize_intraday(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if df is None or df.empty:
        raise PaperIntegrityError(f"NO_INTRADAY_DATA:{symbol}")
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        if symbol in out.columns.get_level_values(-1):
            out = out.xs(symbol, axis=1, level=-1)
        elif symbol in out.columns.get_level_values(0):
            out = out.xs(symbol, axis=1, level=0)
    if "Open" not in out.columns or "Close" not in out.columns:
        raise PaperIntegrityError(f"MISSING_INTRADAY_OHLC:{symbol}")
    idx = pd.DatetimeIndex(out.index)
    if idx.tz is None:
        idx = idx.tz_localize("UTC")
    out.index = idx.tz_convert(NY_TZ)
    out = out.between_time("09:30", "16:00", inclusive="left")[["Open", "Close"]].copy()
    out["Open"] = pd.to_numeric(out["Open"], errors="coerce")
    out["Close"] = pd.to_numeric(out["Close"], errors="coerce")
    out = out.dropna()
    if out.empty:
        raise PaperIntegrityError(f"NO_REGULAR_SESSION_DATA:{symbol}")
    return out


def _fetch_intraday(symbol: str, start: date, end_exclusive: date) -> pd.DataFrame:
    import yfinance as yf
    last: Exception | None = None
    for attempt in range(3):
        try:
            raw = yf.download(
                symbol,
                start=start.isoformat(),
                end=end_exclusive.isoformat(),
                interval="1m",
                auto_adjust=False,
                prepost=False,
                actions=False,
                progress=False,
                threads=False,
            )
            return _normalize_intraday(raw, symbol)
        except Exception as exc:
            last = exc
            if attempt < 2:
                _time.sleep(2 ** attempt)
    raise PaperIntegrityError(f"INTRADAY_FETCH_FAILED:{symbol}:{last}")


def _session_dates(df: pd.DataFrame) -> list[str]:
    return sorted({ts.date().isoformat() for ts in df.index})


def _bar_open(df: pd.DataFrame, session: str, hour: int, minute: int, symbol: str) -> float:
    d = date.fromisoformat(session)
    day = df[df.index.date == d]
    exact = day[(day.index.hour == hour) & (day.index.minute == minute)]
    if exact.empty:
        raise PaperIntegrityError(f"MISSING_{hour:02d}{minute:02d}_BAR:{symbol}:{session}")
    value = float(exact.iloc[0]["Open"])
    if not _positive(value):
        raise PaperIntegrityError(f"INVALID_EXEC_PRICE:{symbol}:{session}:{hour:02d}{minute:02d}")
    return value


def _eod_close(df: pd.DataFrame, session: str, symbol: str) -> float:
    d = date.fromisoformat(session)
    day = df[df.index.date == d]
    if len(day) < 100:
        raise PaperIntegrityError(f"TOO_FEW_MINUTE_BARS:{symbol}:{session}:{len(day)}")
    value = float(day.iloc[-1]["Close"])
    if not _positive(value):
        raise PaperIntegrityError(f"INVALID_EOD_CLOSE:{symbol}:{session}")
    return value


def _fetch_actions(symbol: str, session: date) -> tuple[float, float]:
    import yfinance as yf
    try:
        df = yf.Ticker(symbol).history(
            start=session.isoformat(),
            end=(session + timedelta(days=1)).isoformat(),
            interval="1d",
            auto_adjust=False,
            actions=True,
            prepost=False,
        )
    except Exception as exc:
        raise PaperIntegrityError(f"ACTION_FETCH_FAILED:{symbol}:{exc}") from exc
    if df is None or df.empty:
        return 0.0, 0.0
    dividends = pd.to_numeric(df.get("Dividends", pd.Series([0.0])), errors="coerce").fillna(0.0)
    splits = pd.to_numeric(df.get("Stock Splits", pd.Series([0.0])), errors="coerce").fillna(0.0)
    nonzero = [float(x) for x in splits if float(x) != 0.0]
    if len(nonzero) > 1:
        raise PaperIntegrityError(f"MULTIPLE_SPLITS_ONE_SESSION:{symbol}")
    return float(dividends.sum()), (nonzero[0] if nonzero else 0.0)


def fetch_execution_market(signal_date: str, current_completed_date: str) -> SessionMarket:
    start_signal = date.fromisoformat(signal_date)
    current = date.fromisoformat(current_completed_date)
    if current <= start_signal:
        raise PaperIntegrityError("NO_NEW_COMPLETED_SESSION")
    start = start_signal + timedelta(days=1)
    end = current + timedelta(days=1)
    frames = {s: _fetch_intraday(s, start, end) for s in SYMBOLS}
    common = sorted(set(_session_dates(frames["QQQ"])) & set(_session_dates(frames["TQQQ"])))
    common = [d for d in common if d > signal_date]
    if not common:
        raise PaperIntegrityError("NO_COMMON_EXECUTION_SESSION")
    session = common[0]
    if session != current_completed_date:
        raise PaperIntegrityError(
            f"MISSED_SHADOW_SESSION:expected_execution={session}:current_completed={current_completed_date}"
        )
    p31 = {s: _bar_open(frames[s], session, 9, 31, s) for s in SYMBOLS}
    p32 = {s: _bar_open(frames[s], session, 9, 32, s) for s in SYMBOLS}
    closes = {s: _eod_close(frames[s], session, s) for s in SYMBOLS}
    dividends: dict[str, float] = {}
    splits: dict[str, float] = {}
    session_date = date.fromisoformat(session)
    for s in SYMBOLS:
        dividends[s], splits[s] = _fetch_actions(s, session_date)
    return SessionMarket(session, p31, p32, closes, dividends, splits)


def new_state() -> dict[str, Any]:
    return {
        "version": "0.6",
        "initial_equity": PAPER_INITIAL_EQUITY,
        "cash": PAPER_INITIAL_EQUITY,
        "shares": {"QQQ": 0, "TQQQ": 0},
        "peak_equity": PAPER_INITIAL_EQUITY,
        "last_equity": PAPER_INITIAL_EQUITY,
        "last_executed_signal_date": None,
        "last_mark_session": None,
        "cumulative_fees": 0.0,
        "cumulative_slippage_cost": 0.0,
        "cumulative_dividends": 0.0,
        "trade_count": 0,
    }


def _portfolio_value(state: dict[str, Any], prices: dict[str, float]) -> float:
    return float(state["cash"]) + sum(
        int(state["shares"][s]) * float(prices[s]) for s in SYMBOLS
    )


def _apply_corporate_actions(state: dict[str, Any], market: SessionMarket) -> dict[str, float]:
    credited = 0.0
    for symbol in SYMBOLS:
        split = float(market.split_ratios.get(symbol, 0.0) or 0.0)
        if split:
            adjusted = int(state["shares"][symbol]) * split
            if not math.isclose(adjusted, round(adjusted), rel_tol=0.0, abs_tol=1e-9):
                raise PaperIntegrityError(f"FRACTIONAL_SHARES_FROM_SPLIT:{symbol}:{adjusted}")
            state["shares"][symbol] = int(round(adjusted))
        dividend = float(market.dividends.get(symbol, 0.0) or 0.0)
        if dividend:
            amount = int(state["shares"][symbol]) * dividend
            state["cash"] += amount
            credited += amount
    state["cumulative_dividends"] += credited
    return {"dividends_credited": credited}


def _trade(
    state: dict[str, Any],
    symbol: str,
    side: str,
    qty: int,
    reference_price: float,
    time_et: str,
    session_date: str,
    signal_date: str,
) -> dict[str, Any] | None:
    if qty <= 0:
        return None
    slip = SLIPPAGE_BPS / 10_000.0
    fee_rate = FEE_BPS / 10_000.0
    fill = reference_price * (1.0 + slip if side == "BUY" else 1.0 - slip)
    if side == "SELL":
        qty = min(qty, int(state["shares"][symbol]))
    if qty <= 0:
        return None
    gross = fill * qty
    fee = gross * fee_rate
    if side == "BUY":
        max_qty = int(state["cash"] // (fill * (1.0 + fee_rate)))
        qty = min(qty, max_qty)
        if qty <= 0:
            return None
        gross = fill * qty
        fee = gross * fee_rate
        state["cash"] -= gross + fee
        state["shares"][symbol] += qty
    else:
        state["cash"] += gross - fee
        state["shares"][symbol] -= qty
    slippage_cost = abs(fill - reference_price) * qty
    state["cumulative_fees"] += fee
    state["cumulative_slippage_cost"] += slippage_cost
    state["trade_count"] += 1
    return {
        "execution_session": session_date,
        "signal_date": signal_date,
        "symbol": symbol,
        "side": side,
        "qty": qty,
        "time_et": time_et,
        "reference_price": reference_price,
        "modeled_fill_price": fill,
        "gross_notional": gross,
        "fee": fee,
        "modeled_slippage_cost": slippage_cost,
        "fee_bps": FEE_BPS,
        "slippage_bps": SLIPPAGE_BPS,
    }


def rebalance_if_required(
    state: dict[str, Any],
    signal_report: dict[str, Any],
    market: SessionMarket,
    bootstrap: bool,
) -> list[dict[str, Any]]:
    target = signal_report["latest"]
    weights = {"QQQ": float(target["qqq_weight"]), "TQQQ": float(target["tqqq_weight"])}
    if any(not math.isfinite(w) or w < 0 or w > 1 for w in weights.values()) or sum(weights.values()) > 1.000001:
        raise PaperIntegrityError("INVALID_FROZEN_PAPER_TARGET_WEIGHTS")
    signal_date = target["asof_date"]
    trades: list[dict[str, Any]] = []

    # NO_CHANGE compares successive signals, not the actual portfolio.
    # Reconcile actual holdings even after a missed prior paper session.
    equity31 = _portfolio_value(state, market.prices_0931)
    if not math.isfinite(equity31) or equity31 <= 0:
        raise PaperIntegrityError("INVALID_PAPER_EQUITY_BEFORE_REBALANCE")
    gap31 = max(abs(int(state["shares"][s]) * float(market.prices_0931[s]) / equity31 - weights[s])
                for s in SYMBOLS)
    # Avoid repeated whole-share churn when actual ETF weights are within 50bp.
    if not bootstrap and signal_report.get("action") == "NO_CHANGE" and gap31 <= 0.005:
        return []
    desired31 = {
        s: int(math.floor(weights[s] * equity31 / market.prices_0931[s])) for s in SYMBOLS
    }
    for s in SYMBOLS:
        excess = int(state["shares"][s]) - desired31[s]
        if excess > 0:
            tr = _trade(state, s, "SELL", excess, market.prices_0931[s], "09:31", market.session_date, signal_date)
            if tr:
                trades.append(tr)

    equity32 = _portfolio_value(state, market.prices_0932)
    desired32 = {
        s: int(math.floor(weights[s] * equity32 / market.prices_0932[s])) for s in SYMBOLS
    }
    for s in SYMBOLS:
        shortage = desired32[s] - int(state["shares"][s])
        if shortage > 0:
            tr = _trade(state, s, "BUY", shortage, market.prices_0932[s], "09:32", market.session_date, signal_date)
            if tr:
                trades.append(tr)
    return trades


def mark_session(
    state: dict[str, Any],
    signal_report: dict[str, Any],
    market: SessionMarket,
    trades: list[dict[str, Any]],
    corporate_action_summary: dict[str, float],
    bootstrap: bool,
) -> dict[str, Any]:
    equity = _portfolio_value(state, market.closes)
    state["peak_equity"] = max(float(state["peak_equity"]), equity)
    state["last_equity"] = equity
    state["last_executed_signal_date"] = signal_report["latest"]["asof_date"]
    state["last_mark_session"] = market.session_date
    peak = float(state["peak_equity"])
    drawdown = equity / peak - 1.0 if peak else 0.0
    cumulative_return = equity / float(state["initial_equity"]) - 1.0
    turnover = sum(float(t["gross_notional"]) for t in trades)
    latest = signal_report["latest"]
    tracking_weights = {"QQQ": float(latest["qqq_weight"]), "TQQQ": float(latest["tqqq_weight"])}
    equity32 = _portfolio_value(state, market.prices_0932)
    gap32 = max(abs(int(state["shares"][s]) * float(market.prices_0932[s]) / equity32 - tracking_weights[s])
                for s in SYMBOLS)
    one_share_band = max(float(x) for x in market.prices_0932.values()) / equity32
    if gap32 > max(0.01, one_share_band + 0.005):
        raise PaperIntegrityError(f"PAPER_POST_REBALANCE_TARGET_MISMATCH:{market.session_date}:{gap32:.8f}")
    return {
        "session_date": market.session_date,
        "signal_date": latest["asof_date"],
        "signal_action": signal_report.get("action", "NO_CHANGE"),
        "paper_action": ("BOOTSTRAP_TO_TARGET" if bootstrap else "RECONCILE_ACTUAL_HOLDINGS" if trades and signal_report.get("action", "NO_CHANGE")=="NO_CHANGE" else signal_report.get("action", "NO_CHANGE")),
        "target_level": latest["level"],
        "target_defense": bool(latest["defense_active"]),
        "target_leverage": float(latest["target_leverage"]),
        "target_qqq_weight": float(latest["qqq_weight"]),
        "target_tqqq_weight": float(latest["tqqq_weight"]),
        "target_tracking_gap_after": gap32,
        "qqq_shares": int(state["shares"]["QQQ"]),
        "tqqq_shares": int(state["shares"]["TQQQ"]),
        "cash": float(state["cash"]),
        "qqq_close": float(market.closes["QQQ"]),
        "tqqq_close": float(market.closes["TQQQ"]),
        "equity": equity,
        "cumulative_return": cumulative_return,
        "peak_equity": peak,
        "drawdown": drawdown,
        "trade_count_session": len(trades),
        "turnover_notional": turnover,
        "cumulative_fees": float(state["cumulative_fees"]),
        "cumulative_slippage_cost": float(state["cumulative_slippage_cost"]),
        "cumulative_dividends": float(state["cumulative_dividends"]),
        "dividends_credited_session": float(corporate_action_summary["dividends_credited"]),
        "execution_source": market.source,
        "fee_bps": FEE_BPS,
        "slippage_bps": SLIPPAGE_BPS,
    }

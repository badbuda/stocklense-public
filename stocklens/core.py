from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import date
from typing import Optional, Sequence
import math

LEVEL_LEVERAGE = {1: 1.25, 2: 2.0, 3: 3.0}
TARGET_INVESTED_FRACTION = 0.985
TRADING_START = date(2009, 9, 1)


@dataclass(frozen=True)
class Features:
    close: float
    sma50: float
    sma200: float
    vol20: float
    mom12: float


@dataclass(frozen=True)
class Decision:
    asof_date: str
    level: int
    defense_active: bool
    target_leverage: float
    qqq_weight: float
    tqqq_weight: float
    invested_fraction: float
    features: Features

    def to_dict(self) -> dict:
        out = asdict(self)
        out["features"] = asdict(self.features)
        return out


def compute_features(closes: Sequence[float]) -> Features:
    if len(closes) < 253:
        raise ValueError("Need at least 253 completed daily closes")

    x = [float(v) for v in closes]
    if any((not math.isfinite(v) or v <= 0) for v in x[-253:]):
        raise ValueError("Invalid close in latest 253-session feature window")

    close = x[-1]
    sma50 = sum(x[-50:]) / 50.0
    sma200 = sum(x[-200:]) / 200.0

    rets = [x[i] / x[i - 1] - 1.0 for i in range(len(x) - 20, len(x))]
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    vol20 = math.sqrt(max(0.0, var)) * math.sqrt(252.0)
    mom12 = close / x[-253] - 1.0

    return Features(close, sma50, sma200, vol20, mom12)


def next_level(features: Features, previous_level: Optional[int]) -> int:
    prev = previous_level if previous_level is not None else 1

    risk_on = prev > 1
    trend_on = (
        features.close >= features.sma200 * 0.99
        if risk_on
        else features.close > features.sma200 * 1.01
    )

    if not trend_on:
        return 1

    if prev == 3:
        return 2 if features.vol20 >= 0.32 else 3

    if prev == 2:
        if features.vol20 < 0.28:
            return 3
        if features.vol20 >= 0.42:
            return 1
        return 2

    if features.vol20 < 0.28:
        return 3
    if features.vol20 < 0.38:
        return 2
    return 1


def defense_active(features: Features) -> bool:
    return features.sma50 < features.sma200 and features.mom12 <= 0.0


def weights_for_leverage(leverage: float) -> tuple[float, float]:
    if leverage <= 0:
        return 0.0, 0.0

    lev = max(1.0, min(3.0, float(leverage)))
    tqqq = (lev - 1.0) / 2.0
    qqq = 1.0 - tqqq
    return qqq, tqqq


def replay_levels(closes: Sequence[float], dates: Sequence[str]) -> list[Decision]:
    """
    Exact StockLens 8.0 replay semantics:
    - history before 2009-09-01 is feature warmup only
    - hysteresis state starts as None on the first trading decision
    - all later state is reconstructed sequentially from 2009 onward
    """
    if len(closes) != len(dates):
        raise ValueError("closes and dates must have identical length")

    parsed_dates = [date.fromisoformat(str(d)[:10]) for d in dates]

    start_idx = None
    for i, d in enumerate(parsed_dates):
        if d >= TRADING_START:
            start_idx = i
            break

    if start_idx is None:
        raise ValueError("History does not reach StockLens trading start")
    if start_idx < 252:
        raise ValueError(
            "Insufficient pre-2009 warmup. Need >=252 completed sessions before trading start."
        )

    level: Optional[int] = None
    out: list[Decision] = []

    for i in range(start_idx, len(closes)):
        f = compute_features(closes[: i + 1])
        level = next_level(f, level)
        defense = defense_active(f)
        leverage = 0.0 if defense else LEVEL_LEVERAGE[level]
        qqq, tqqq = weights_for_leverage(leverage)

        out.append(
            Decision(
                asof_date=str(dates[i]),
                level=level,
                defense_active=defense,
                target_leverage=leverage,
                qqq_weight=qqq * TARGET_INVESTED_FRACTION,
                tqqq_weight=tqqq * TARGET_INVESTED_FRACTION,
                invested_fraction=0.0 if defense else TARGET_INVESTED_FRACTION,
                features=f,
            )
        )

    return out

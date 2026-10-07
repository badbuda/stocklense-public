from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Sequence, Mapping, Any

@dataclass(frozen=True)
class BacktestRequest:
    strategy_id: str
    initial_capital: float = 100000.0
    monthly_contribution: float = 3500.0
    transaction_cost_bps: float = 5.0
    start: str | None = None
    end: str | None = None

class StrategyAdapter(Protocol):
    strategy_id: str
    evidence_class: str
    def validate_rows(self, rows: Sequence[Mapping[str, Any]]) -> None: ...
    def target_exposure(self, previous: Mapping[str, Any], current: Mapping[str, Any]) -> float: ...
    def transaction_turnover(self, previous: Mapping[str, Any], current: Mapping[str, Any], prior_applied_exposure: float, applied_exposure: float) -> float: ...

@dataclass(frozen=True)
class FrozenExposureReplayAdapter:
    """Adapter for the existing frozen StockLens replay.

    This is intentionally only an interface seam for M2. It preserves the
    existing M1 accounting implementation and does not claim a new execution
    engine or LEAN parity.
    """
    strategy_id: str = "STOCKLENS_8_FROZEN_REPLAY"
    evidence_class: str = "REPLAY_APPROXIMATION"

    def validate_rows(self, rows):
        if len(rows) < 2:
            raise ValueError("BACKTEST_REPLAY_TOO_SHORT")
        required=("date","close","leverage")
        for i,row in enumerate(rows):
            missing=[k for k in required if row.get(k) is None]
            if missing:
                raise ValueError(f"BACKTEST_ROW_MISSING:{i}:{','.join(missing)}")

    def target_exposure(self, previous, current):
        # Existing replay semantics apply the prior completed session's target
        # leverage to the next session return.
        return float(previous["leverage"])

    def transaction_turnover(self, previous, current, prior_applied_exposure, applied_exposure):
        # Preserve frozen M1 semantics: costs occur only on explicit event rows,
        # after the current market move, using current-vs-prior target delta.
        if not current.get("event"):
            return 0.0
        return abs(float(current["leverage"]) - float(previous["leverage"]))

def stocklens_8_request(initial=100000.0, monthly=3500.0, cost_bps=5.0, start=None, end=None):
    return BacktestRequest(
        strategy_id="STOCKLENS_8_FROZEN_REPLAY",
        initial_capital=float(initial),
        monthly_contribution=float(monthly),
        transaction_cost_bps=float(cost_bps),
        start=start,
        end=end,
    )

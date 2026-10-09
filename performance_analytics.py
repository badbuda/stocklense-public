from __future__ import annotations

import csv
import json
import math
from pathlib import Path


def _rows(path):
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        return []
    with p.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _initial_equity(path, rows):
    """Use the pre-trade capital, never the first marked-to-market equity."""
    state = Path(path)
    if not state.exists():
        raise ValueError("PAPER_INITIAL_EQUITY_STATE_MISSING")
    data = json.loads(state.read_text(encoding="utf-8"))
    initial = data.get("initial_equity")
    if isinstance(initial, bool):
        raise ValueError("PAPER_INITIAL_EQUITY_INVALID")
    try:
        capital = float(initial)
    except (TypeError, ValueError) as exc:
        raise ValueError("PAPER_INITIAL_EQUITY_INVALID") from exc
    if not math.isfinite(capital) or capital <= 0:
        raise ValueError("PAPER_INITIAL_EQUITY_INVALID")
    if rows:
        last = rows[-1]
        ledger_equity = _f(last.get("equity"), float("nan"))
        reported = _f(last.get("cumulative_return"), float("nan"))
        expected = ledger_equity / capital - 1.0
        if not all(map(math.isfinite, (ledger_equity, reported, expected))):
            raise ValueError("PAPER_LEDGER_RETURN_INVALID")
        if not math.isclose(reported, expected, abs_tol=1e-8, rel_tol=1e-8):
            raise ValueError("PAPER_LEDGER_INCEPTION_RETURN_MISMATCH")
    return capital


def build_performance(out="shadow_history/performance.json",
                      ledger_path="paper_portfolio/ledger.csv",
                      state_path="paper_portfolio/state.json"):
    rows = _rows(ledger_path)
    result = {"status": "WAITING_FOR_PROSPECTIVE_DATA", "sessions": len(rows)}
    if rows:
        initial = _initial_equity(state_path, rows)
        equities = [_f(r.get("equity"), float("nan")) for r in rows]
        if not all(math.isfinite(e) and e > 0 for e in equities):
            raise ValueError("PAPER_LEDGER_EQUITY_INVALID")
        rets = [equities[i] / equities[i-1] - 1 for i in range(1, len(equities))]
        peak = max([initial, *equities])
        current = equities[-1]
        max_dd = min((_f(r.get("drawdown"), 0) for r in rows), default=0)
        vol = (math.sqrt(252) * math.sqrt(
            sum((x - (sum(rets) / len(rets))) ** 2 for x in rets) / (len(rets) - 1)
        )) if len(rets) > 1 else None
        result = {
            "status": "ACTIVE", "sessions": len(rows),
            "start_equity": initial, "current_equity": current,
            "cumulative_return": current / initial - 1,
            "peak_equity": peak, "max_drawdown": max_dd,
            "annualized_volatility": vol,
            "cumulative_fees": _f(rows[-1].get("cumulative_fees")),
            "cumulative_slippage_cost": _f(rows[-1].get("cumulative_slippage_cost")),
            "trade_count": sum(int(_f(r.get("trade_count_session"))) for r in rows),
            "total_return_pct": (current / initial - 1) * 100,
            "max_drawdown_pct": max_dd * 100,
            "annualized_volatility_pct": vol * 100 if vol is not None else None,
            "fee_drag_pct": _f(rows[-1].get("cumulative_fees")) / initial * 100,
            "slippage_drag_pct": _f(rows[-1].get("cumulative_slippage_cost")) / initial * 100,
            "return_basis": "PAPER_STATE_INITIAL_EQUITY",
        }
    p = Path(out)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(build_performance(), indent=2))

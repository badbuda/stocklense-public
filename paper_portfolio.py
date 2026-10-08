from __future__ import annotations

import csv
import json
import os
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from stocklens.paper import (
    PaperIntegrityError,
    fetch_execution_market,
    mark_session,
    new_state,
    rebalance_if_required,
    _apply_corporate_actions,
)

STATE_DIR = Path("paper_portfolio")
STATE_PATH = STATE_DIR / "state.json"
LEDGER_PATH = STATE_DIR / "ledger.csv"
TRADES_PATH = STATE_DIR / "trades.csv"
LATEST_MD_PATH = STATE_DIR / "latest.md"
GAPS_PATH = STATE_DIR / "evidence_gaps.csv"
NY_TZ = ZoneInfo("America/New_York")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _append_csv(path: Path, row: dict[str, Any]) -> None:
    exists = path.exists() and path.stat().st_size > 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(row.keys()))
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def _existing_session(path: Path, session_date: str) -> bool:
    if not path.exists() or path.stat().st_size == 0:
        return False
    with path.open("r", encoding="utf-8", newline="") as fh:
        return any(r.get("session_date") == session_date for r in csv.DictReader(fh))


def _completed_nyse_dates(after_date: str, through_date: str) -> list[str]:
    """Enumerate all missed sessions from the exchange calendar, never weekends."""
    import exchange_calendars as xcals
    calendar = xcals.get_calendar("XNYS")
    return [str(x.date()) for x in calendar.sessions_in_range(after_date, through_date)
            if str(x.date()) > after_date]


def _signal_precedes_session(signal_report: dict[str, Any], session_date: str) -> bool:
    """A paper fill counts only if its signal existed before that session opened."""
    raw = signal_report.get("generated_at_utc")
    if not raw:
        raise PaperIntegrityError("MISSING_SIGNAL_GENERATION_TIMESTAMP")
    try:
        generated = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError as exc:
        raise PaperIntegrityError(f"INVALID_SIGNAL_GENERATION_TIMESTAMP:{raw}") from exc
    if generated.tzinfo is None:
        raise PaperIntegrityError("NAIVE_SIGNAL_GENERATION_TIMESTAMP")

    session_open = datetime.combine(
        date.fromisoformat(session_date),
        time(9, 30),
        tzinfo=NY_TZ,
    )
    return generated.astimezone(timezone.utc) < session_open.astimezone(timezone.utc)


def _render_latest(row: dict[str, Any], trades: list[dict[str, Any]]) -> str:
    return f"""# StockLens 8.0 Paper Portfolio

**Execution session:** {row['session_date']}  
**Signal date:** {row['signal_date']}  
**Paper action:** {row['paper_action']}  
**Target:** Level {row['target_level']} / {'Defense ON' if row['target_defense'] else 'Defense OFF'} / {row['target_leverage']:.2f}x

## Portfolio

- Equity: **${row['equity']:,.2f}**
- Cumulative return: **{row['cumulative_return'] * 100:.2f}%**
- Drawdown: **{row['drawdown'] * 100:.2f}%**
- Cash: **${row['cash']:,.2f}**
- QQQ shares: **{row['qqq_shares']}**
- TQQQ shares: **{row['tqqq_shares']}**

## Execution accounting

- Trades this session: **{len(trades)}**
- Turnover: **${row['turnover_notional']:,.2f}**
- Cumulative fees (2 bp): **${row['cumulative_fees']:,.2f}**
- Cumulative modeled slippage (10 bp/side): **${row['cumulative_slippage_cost']:,.2f}**
- Cumulative dividends credited: **${row['cumulative_dividends']:,.2f}**
- Execution reference: **Yahoo 1-minute raw market data**

No broker orders are sent. This is a prospective paper ledger only.
"""


def reconcile(
    current_signal_path: str = "output/latest_signal.json",
    prior_signal_path: str = "shadow_history/latest.json",
) -> dict[str, str]:
    current_path = Path(current_signal_path)
    prior_path = Path(prior_signal_path)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    if not prior_path.exists():
        return {"paper_updated": "false", "paper_status": "NO_PRIOR_PERSISTED_SIGNAL"}

    current = _read_json(current_path)
    prior = _read_json(prior_path)
    current_date = current["latest"]["asof_date"]
    prior_date = prior["latest"]["asof_date"]

    if current_date <= prior_date:
        return {"paper_updated": "false", "paper_status": "WAITING_FOR_NEXT_COMPLETED_SESSION"}

    state = _read_json(STATE_PATH) if STATE_PATH.exists() else new_state()
    bootstrap = state.get("last_executed_signal_date") is None

    if not bootstrap and prior_date <= state["last_executed_signal_date"]:
        return {"paper_updated": "false", "paper_status": "SIGNAL_ALREADY_RECONCILED"}

    try:
        market = fetch_execution_market(prior_date, current_date)
    except PaperIntegrityError as exc:
        message = str(exc)
        if message.startswith("MISSED_SHADOW_SESSION:"):
            fields = dict(part.split("=", 1) for part in message.split(":")[1:])
            missed = _completed_nyse_dates(prior_date, fields["current_completed"])
            if not missed or missed[0] != fields["expected_execution"]:
                raise PaperIntegrityError("MISSED_SESSION_CALENDAR_MISMATCH")
            for missed_session in missed:
                gap = {
                    "session_date": missed_session,
                    "signal_date": prior_date,
                    "detected_completed_session": fields["current_completed"],
                    "status": "MISSED_NO_BACKFILL",
                }
                if not _existing_session(GAPS_PATH, gap["session_date"]):
                    _append_csv(GAPS_PATH, gap)
            return {
                "paper_updated": "false",
                "paper_status": "MISSED_SESSION_RECORDED_NO_BACKFILL",
                "missed_session": missed[0],
                "missed_sessions_count": str(len(missed)),
            }
        raise

    if not _signal_precedes_session(prior, market.session_date):
        # Even during bootstrap a late signal is a MISSED execution, never
        # an unqualified "waiting" status. Preserve the gap, do not backfill.
        gap = {
            "session_date": market.session_date,
            "signal_date": prior_date,
            "detected_completed_session": current_date,
            "status": "MISSED_LATE_SIGNAL_NO_BACKFILL",
        }
        if not _existing_session(GAPS_PATH, gap["session_date"]):
            _append_csv(GAPS_PATH, gap)
        return {
            "paper_updated": "false",
            "paper_status": "MISSED_LATE_SIGNAL_RECORDED_NO_BACKFILL",
            "missed_session": market.session_date,
            "late_signal_date": prior_date,
        }

    if _existing_session(LEDGER_PATH, market.session_date):
        raise PaperIntegrityError(f"DUPLICATE_PAPER_SESSION:{market.session_date}")

    corporate_summary = _apply_corporate_actions(state, market)
    trades = rebalance_if_required(state, prior, market, bootstrap=bootstrap)
    row = mark_session(state, prior, market, trades, corporate_summary, bootstrap=bootstrap)

    for trade in trades:
        _append_csv(TRADES_PATH, trade)
    _append_csv(LEDGER_PATH, row)

    STATE_PATH.write_text(json.dumps(state, indent=2), encoding="utf-8")
    LATEST_MD_PATH.write_text(_render_latest(row, trades), encoding="utf-8")

    return {
        "paper_updated": "true",
        "paper_status": "OK",
        "paper_session": market.session_date,
        "paper_equity": f"{row['equity']:.2f}",
        "paper_drawdown": f"{row['drawdown']:.8f}",
        "paper_trades": str(len(trades)),
    }


def main() -> int:
    result = reconcile()
    gh_out = os.environ.get("GITHUB_OUTPUT")
    if gh_out:
        with open(gh_out, "a", encoding="utf-8") as fh:
            for key, value in result.items():
                fh.write(f"{key}={value}\n")
    for key, value in result.items():
        print(f"{key}={value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

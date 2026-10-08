from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .core import replay_levels
from .data import load_qqq_history


def fmt_pct(x: float) -> str:
    return f"{x * 100:.2f}%"


def build_report(csv_path: str | None = None) -> dict:
    df, completion_audit = load_qqq_history(csv_path=csv_path)
    dates = [d.date().isoformat() for d in df["Date"]]
    closes = [float(x) for x in df["Close"]]

    decisions = replay_levels(closes, dates)
    latest = decisions[-1]
    previous = decisions[-2] if len(decisions) > 1 else None

    action = "NO_CHANGE"
    if previous is None or previous.target_leverage != latest.target_leverage:
        action = "REBALANCE_NEXT_SESSION"
    if previous is not None and previous.defense_active != latest.defense_active:
        action = "ENTER_CASH_NEXT_SESSION" if latest.defense_active else "EXIT_CASH_NEXT_SESSION"

    return {
        "version": "8.0.2-shadow-completed-session-guard",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "mode": "SHADOW_ONLY_NO_BROKER_ACTIONS",
        "signal_source": "QQQ_ADJUSTED_DAILY_CLOSE",
        "state_replay": "EXACT_FROM_2009_09_01_WITH_PRESTART_WARMUP",
        "latest": latest.to_dict(),
        "previous": previous.to_dict() if previous else None,
        "action": action,
        "execution_plan": {
            "signal_basis": "LATEST_COMPLETED_QQQ_DAILY_CLOSE",
            "reductions": "NEXT_SESSION_OPEN_PLUS_1_MIN",
            "additions": "NEXT_SESSION_OPEN_PLUS_2_MIN",
            "broker_actions_enabled": False,
        },
        "data_audit": {
            "rows": len(df),
            "first_date": dates[0],
            "last_date": dates[-1],
            "last_close": closes[-1],
            **completion_audit,
        },
    }


def render_markdown(report: dict) -> str:
    x = report["latest"]
    f = x["features"]
    prev = report.get("previous")

    changed = (
        prev is None
        or prev["target_leverage"] != x["target_leverage"]
        or prev["defense_active"] != x["defense_active"]
    )

    return f"""# StockLens 8.0 Shadow Signal

**As of completed QQQ close:** {x['asof_date']}  
**Action:** {report['action']}  
**Changed vs prior session:** {'YES' if changed else 'NO'}

## Current state

- Level: **{x['level']}**
- Defense: **{'ON' if x['defense_active'] else 'OFF'}**
- Target leverage: **{x['target_leverage']:.2f}x**
- QQQ target weight: **{fmt_pct(x['qqq_weight'])}**
- TQQQ target weight: **{fmt_pct(x['tqqq_weight'])}**
- Cash / buffer: **{fmt_pct(1.0 - x['qqq_weight'] - x['tqqq_weight'])}**

## Features

- QQQ adjusted close: **{f['close']:.4f}**
- SMA50: **{f['sma50']:.4f}**
- SMA200: **{f['sma200']:.4f}**
- VOL20 annualized: **{fmt_pct(f['vol20'])}**
- MOM12: **{fmt_pct(f['mom12'])}**

## Frozen execution plan

Signal uses the latest **completed** QQQ daily close only.

If the target changed:
- reductions / sells: next session open + 1 minute
- additions / buys: next session open + 2 minutes

**Broker integration is disabled. This is shadow-only.**

## Data audit

- Rows: {report['data_audit']['rows']}
- First date: {report['data_audit']['first_date']}
- Last date: {report['data_audit']['last_date']}
- Source: QQQ adjusted daily data
- Raw last date: {report['data_audit'].get('raw_last_date')}
- Last completed date used: {report['data_audit'].get('last_completed_date')}
- Dropped incomplete current session: **{report['data_audit'].get('dropped_incomplete_current_session')}**
- NY validation time: {report['data_audit'].get('ny_time_at_validation')}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", help="Optional local QQQ CSV for deterministic replay")
    ap.add_argument("--out-dir", default="output")
    args = ap.parse_args()

    report = build_report(csv_path=args.csv)
    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    (out / "latest_signal.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    (out / "latest_signal.md").write_text(
        render_markdown(report), encoding="utf-8"
    )

    print(render_markdown(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

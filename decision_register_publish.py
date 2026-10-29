"""Publish a source-honest decision register, never a synthetic Paper history.

Inputs: immutable dated Shadow reports + separately marked observed-ETF
daily-open historical execution proxy + legacy Paper archive.
Every archived decision retains its own timestamp and source path.
Missing days remain missing. No AWS assertions without AWS receipts.
"""
from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SHADOW = ROOT / "shadow_history"
HISTORY = ROOT / "docs/portal-history.json"
PAPER = ROOT / "paper_portfolio/latest_session.json"
OUT = ROOT / "docs/decision-register.json"
KIND = "STOCKLENS_SOURCE_SEPARATED_DECISION_REGISTER_V1"


def json_file(path: Path) -> dict:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError(f"INVALID_JSON_OBJECT:{path}")
    return obj


def extract_shadow(path: Path) -> dict:
    obj = json_file(path)
    latest = obj.get("latest", {})
    day = latest.get("asof_date")
    if (day != path.stem or date.fromisoformat(day).isoformat() != day
        or obj.get("mode") != "SHADOW_ONLY_NO_BROKER_ACTIONS"
        or obj.get("execution_plan", {}).get("broker_actions_enabled") is not False
        or obj.get("signal_source") != "QQQ_ADJUSTED_DAILY_CLOSE"):
        raise ValueError("INVALID_SHADOW_ARCHIVE:" + path.name)
    at = datetime.fromisoformat(obj["generated_at_utc"].replace("Z", "+00:00"))
    if at.tzinfo is None or at.date() < date.fromisoformat(day):
        raise ValueError("INVALID_SIGNAL_TIMESTAMP:" + day)
    lev = latest.get("target_leverage")
    if (latest.get("level") not in (1, 2, 3)
        or type(latest.get("defense_active")) is not bool
        or lev not in (0, 1.25, 2, 3)):
        raise ValueError("INVALID_FROZEN_DECISION:" + day)
    if obj.get("action") not in (
        "NO_CHANGE", "REBALANCE_NEXT_SESSION", "ENTER_CASH_NEXT_SESSION",
        "EXIT_CASH_NEXT_SESSION"
    ):
        raise ValueError("INVALID_SHADOW_ACTION:" + day)
    return {
        "session": day, "created_at_utc": obj["generated_at_utc"],
        "action": obj["action"], "level": latest["level"],
        "defense": latest["defense_active"], "target_leverage": lev,
        "target_qqq_weight": latest.get("qqq_weight"),
        "target_tqqq_weight": latest.get("tqqq_weight"),
        "qqq_adjusted_close": latest.get("features", {}).get("close"),
        "source": "shadow_history/" + path.name,
        "provenance": "ARCHIVED_GITHUB_SHADOW_SIGNAL_NOT_AWS_ORDER",
        "broker_fills": False,
    }


def build(paths: list[Path], history: dict, paper: dict) -> dict:
    rows = [extract_shadow(p) for p in sorted(paths)]
    days = [x["session"] for x in rows]
    if not rows or days != sorted(set(days)):
        raise ValueError("SHADOW_ARCHIVE_EMPTY_DUPLICATE_OR_UNSORTED")
    historical = history.get("period", {})
    daily = history.get("daily", [])
    if (history.get("evidence") != "REAL_QQQ_TQQQ_ADJUSTED_DAILY_OPEN_EXECUTION_PROXY"
        or history.get("observed_ohlc_available") is not True
        or history.get("live_trading_authorized") is not False
        or history.get("full_lean_broker_parity") is not False
        or len(daily) != historical.get("sessions") or len(daily) < 100
        or daily[0].get("date") != historical.get("start")
        or daily[-1].get("date") != historical.get("end")
        or history.get("updated_session") != historical.get("end")):
        raise ValueError("INVALID_HISTORICAL_PROXY_FEED")
    last_paper = paper.get("session_date")
    if (paper.get("broker_fills_observed") is not False
        or paper.get("row", {}).get("session_date") != last_paper
        or not last_paper):
        raise ValueError("INVALID_LEGACY_PAPER_ARCHIVE")
    return {
        "schema_version": 1, "kind": KIND,
        "source_cutoff_signal_session": days[-1],
        "generated_at_utc": rows[-1]["created_at_utc"],
        "archived_signal_count": len(rows),
        "archived_signals": rows,
        "archive_is_contiguous": False,
        "missing_signal_days_filled": False,
        "historical_execution_proxy": {
            "source": "portal-history.json",
            "start": historical["start"], "end": historical["end"],
            "sessions": len(daily),
            "label": "HISTORICAL_MODELED_DAILY_OPEN_PROXY_NOT_OBSERVED_BROKER_FILLS",
            "note": "These rows use observed QQQ/TQQQ adjusted daily OHLC and modeled next-open execution; not actual Shadow receipts or minute-level fills.",
        },
        "legacy_paper": {
            "source": "paper_portfolio/latest_session.json",
            "last_recorded_session": last_paper,
            "last_recorded_equity_usd": paper["row"].get("equity"),
            "broker_fills_observed": False,
            "status": "HISTORICAL_MODELLED_ARCHIVE_NOT_CURRENT",
        },
        "aws_st": {
            "status": "REQUIRES_AUTHENTICATED_AWS_READBACK",
            "note": "The ST Signal EventBridge rule was enabled by the operator on 2026-10-29, but this GitHub file cannot certify subsequent AWS invocations or S3 receipts.",
        },
        "aws_prod": {
            "status": "NOT_APPROVED_FOR_EXECUTION",
            "note": "Resource provisioning does not imply active production Paper or brokerage access.",
        },
        "automatic_trading_authorized": False,
        "broker_orders_executed_by_this_report": False,
    }


def main() -> None:
    paths = sorted(SHADOW.glob("20??-??-??.json"))
    out = build(paths, json_file(HISTORY), json_file(PAPER))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"DECISION_REGISTER_PASS:archived={len(out['archived_signals'])}:historical={out['historical_execution_proxy']['sessions']}:asof={out['source_cutoff_signal_session']}:no_paper_backfill")


if __name__ == "__main__":
    main()

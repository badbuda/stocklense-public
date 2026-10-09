"""Export read-only DynamoDB signal/paper receipts to auditable CSV.

Uses only the pre-existing GitHub OIDC role's DynamoDB GetItem access.
Each completed XNYS session has two immutable partition keys: YYYY-MM-DD
and YYYY-MM-DD#PAPER. Missing sessions remain explicit; never backfill fills.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

FIRST_FORWARD_DATE = "2026-10-08"
FIELDS = [
    "session_date", "status", "signal_recorded_utc", "paper_recorded_utc",
    "signal_level", "defense_active", "target_leverage",
    "signal_qqq_weight_pct", "signal_tqqq_weight_pct", "signal_action",
    "paper_action", "paper_execution_source", "qqq_shares", "tqqq_shares",
    "cash_usd", "paper_equity_usd", "paper_cumulative_return_pct",
    "paper_drawdown_pct", "paper_trade_count", "paper_cumulative_fees_usd",
    "paper_cumulative_slippage_usd", "signal_sha256", "paper_sha256",
    "broker_orders_authorized", "broker_fills_observed",
]
TRADE_FIELDS = [
    "session_date", "signal_date", "symbol", "side", "time_et", "qty",
    "reference_price", "modeled_fill_price", "fee", "modeled_slippage_cost",
]


def _maybe(value):
    return "" if value is None else value


def _pct(value):
    return "" if value is None else round(float(value) * 100, 6)


def get_item(table: str, key: str) -> dict | None:
    """Intentionally avoid Scan/Query/PutItem or broadening existing IAM."""
    result = subprocess.run(
        ["aws", "dynamodb", "get-item", "--table-name", table,
         "--key", json.dumps({"session_date": {"S": key}}),
         "--consistent-read", "--output", "json"],
        check=True, capture_output=True, text=True, timeout=25,
    )
    return json.loads(result.stdout).get("Item")


def decode_signal(item: dict | None, day: str) -> dict | None:
    if item is None:
        return None
    if item.get("broker_orders_authorized", {}).get("BOOL") is not False:
        raise ValueError(f"{day}: UNSAFE_SIGNAL_BROKER_FLAG")
    raw = item["signal_json"]["S"]
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if sha != item["signal_sha256"]["S"]:
        raise ValueError(f"{day}: SIGNAL_SHA256_MISMATCH")
    data = json.loads(raw)
    if data.get("mode") != "SHADOW_ONLY_NO_BROKER_ACTIONS":
        raise ValueError(f"{day}: NOT_PAPER_ONLY")
    if data.get("latest", {}).get("asof_date") != day:
        raise ValueError(f"{day}: SIGNAL_DATE_MISMATCH")
    return {"value": data, "sha": sha,
            "recorded_at": item.get("recorded_at_utc", {}).get("S", "")}


def decode_paper(item: dict | None, day: str) -> dict | None:
    if item is None:
        return None
    if item.get("broker_orders_authorized", {}).get("BOOL") is not False:
        raise ValueError(f"{day}: UNSAFE_PAPER_BROKER_FLAG")
    if item.get("broker_fills_observed", {}).get("BOOL") is not False:
        raise ValueError(f"{day}: FALSE_OBSERVED_BROKER_FILLS")
    raw = item["paper_evidence_json"]["S"]
    sha = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    if sha != item["paper_sha256"]["S"]:
        raise ValueError(f"{day}: PAPER_SHA256_MISMATCH")
    data = json.loads(raw)
    row = data["row"]
    trades = data.get("trs")
    if row.get("session_date") != day or row.get("execution_source") != "YFINANCE_1M_RAW":
        raise ValueError(f"{day}: INVALID_PAPER_SESSION_OR_SOURCE")
    if not isinstance(trades, list) or len(trades) != int(row["trade_count_session"]):
        raise ValueError(f"{day}: INVALID_PAPER_TRADE_COUNT")
    if any(tr.get("execution_session") != day for tr in trades):
        raise ValueError(f"{day}: INVALID_PAPER_TRADE_SESSION")
    return {"value": data, "sha": sha,
            "recorded_at": item.get("recorded_at_utc", {}).get("S", "")}


def inspect_session(day: str, signal_item: dict | None,
                    paper_item: dict | None) -> tuple[dict, list[dict]]:
    signal = decode_signal(signal_item, day)
    paper = decode_paper(paper_item, day)
    status = ("PASS" if signal and paper else
              "MISSING_SIGNAL" if paper else
              "MISSING_PAPER" if signal else "MISSING_BOTH")
    output = dict.fromkeys(FIELDS, "")
    output.update(session_date=day, status=status,
                  broker_orders_authorized=False, broker_fills_observed=False)
    trades = []
    if signal:
        obj = signal["value"]
        v = obj["latest"]
        output.update(
            signal_recorded_utc=signal["recorded_at"], signal_sha256=signal["sha"],
            signal_level=_maybe(v.get("level")),
            defense_active=_maybe(v.get("defense_active")),
            target_leverage=_maybe(v.get("target_leverage")),
            signal_qqq_weight_pct=_pct(v.get("qqq_weight")),
            signal_tqqq_weight_pct=_pct(v.get("tqqq_weight")),
            signal_action=_maybe(obj.get("action")),
        )
    if paper:
        obj = paper["value"]
        row = obj["row"]
        output.update(
            paper_recorded_utc=paper["recorded_at"], paper_sha256=paper["sha"],
            paper_action=_maybe(row.get("paper_action")),
            paper_execution_source=row["execution_source"],
            qqq_shares=_maybe(row.get("qqq_shares")),
            tqqq_shares=_maybe(row.get("tqqq_shares")),
            cash_usd=_maybe(row.get("cash")),
            paper_equity_usd=_maybe(row.get("equity")),
            paper_cumulative_return_pct=_pct(row.get("cumulative_return")),
            paper_drawdown_pct=_pct(row.get("drawdown")),
            paper_trade_count=len(obj["trs"]),
            paper_cumulative_fees_usd=_maybe(row.get("cumulative_fees")),
            paper_cumulative_slippage_usd=_maybe(row.get("cumulative_slippage_cost")),
        )
        for tr in obj["trs"]:
            trades.append({key: _maybe(tr.get(key)) for key in TRADE_FIELDS} |
                          {"session_date": day})
    return output, trades


def exchange_sessions(start: str, end: str, cap: int) -> list[str]:
    import exchange_calendars as xcals
    if start > end:
        return []
    cal = xcals.get_calendar("XNYS")
    dates = [s.date().isoformat() for s in cal.sessions_in_range(start, end)]
    return dates[-cap:]


def write_csv(path: Path, headers: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(file, fieldnames=headers)
        writer.writeheader()
        writer.writerows(rows)


def export(table: str, output_dir: Path, sessions: list[str],
           fetch=get_item) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    records, trades, failures = [], [], []
    for day in sessions:
        try:
            row, session_trades = inspect_session(
                day, fetch(table, day), fetch(table, day + "#PAPER"))
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            failures.append(f"{day}: {exc}")
            row = dict.fromkeys(FIELDS, "")
            row.update(session_date=day, status="INVALID_EVIDENCE")
            session_trades = []
        records.append(row)
        trades.extend(session_trades)
    write_csv(output_dir / "sessions.csv", FIELDS, records)
    write_csv(output_dir / "trades.csv", TRADE_FIELDS, trades)
    counts = {label: sum(row["status"] == label for row in records)
              for label in ["PASS", "MISSING_SIGNAL", "MISSING_PAPER",
                            "MISSING_BOTH", "INVALID_EVIDENCE"]}
    summary = {
        "schema_version": 1, "kind": "STOCKLENS_AWS_READ_ONLY_JOURNAL_EXPORT",
        "source": "DYNAMODB_CONSISTENT_GETITEM_VIA_GITHUB_OIDC",
        "first_session": sessions[0] if sessions else None,
        "last_session": sessions[-1] if sessions else None,
        "market_sessions_checked": len(records), "trade_receipts": len(trades),
        "statuses": counts, "errors": failures,
        "all_sessions_pass": bool(records) and counts["PASS"] == len(records),
        "broker_fills_observed": False, "live_trading_authorized": False,
        "note": "Paper execution uses modeled minute-bar opens, NOT actual broker fills. Missing sessions are not backfilled.",
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--table", required=True)
    parser.add_argument("--out", default="aws-journal-export")
    parser.add_argument("--start", default=FIRST_FORWARD_DATE)
    parser.add_argument("--max-sessions", type=int, default=60)
    parser.add_argument("--through", default=None)
    options = parser.parse_args()
    if not 1 <= options.max_sessions <= 252:
        parser.error("--max-sessions must be in 1..252")
    yesterday = (datetime.now(ZoneInfo("America/New_York")).date()
                 - timedelta(days=1)).isoformat()
    through = min(options.through or yesterday, yesterday)
    sessions = exchange_sessions(options.start, through, options.max_sessions)
    summary = export(options.table, Path(options.out), sessions)
    print(json.dumps(summary, ensure_ascii=False))
    if not summary["all_sessions_pass"]:
        raise SystemExit("AWS_JOURNAL_EXPORT_HAS_MISSING_OR_INVALID_SESSIONS")


if __name__ == "__main__":
    main()

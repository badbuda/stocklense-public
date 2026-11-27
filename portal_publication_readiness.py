#!/usr/bin/env python3
"""Check dashboard publication freshness using archive or active modeled Paper evidence."""
from __future__ import annotations

import argparse
from datetime import date, datetime, timezone
import json
from pathlib import Path
import sys

KIND = "STOCKLENS_GITHUB_PUBLICATION_READINESS_V1"
MAX_AGE_DAYS = 4
MIN_PAPER_SESSIONS = 2


def parse_date(value, label, issues):
    if not isinstance(value, str):
        issues.append("MISSING_OR_INVALID_DATE:" + label)
        return None
    try:
        d = date.fromisoformat(value)
        if d.isoformat() != value:
            raise ValueError("noncanonical")
        return d
    except ValueError:
        issues.append("MISSING_OR_INVALID_DATE:" + label)
        return None


def assess(data, history, risk, now=None):
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        raise ValueError("CLOCK_MUST_BE_TIMEZONE_AWARE")
    today = now.astimezone(timezone.utc).date()
    if not all(isinstance(x, dict) for x in (data, history, risk)):
        raise ValueError("JSON_OBJECT_REQUIRED")
    issues = []
    signal = (data.get("signal") or {})
    paper = (data.get("paper") or {})
    latest = (paper.get("latest") or {})
    period = (risk.get("period") or {})
    raw = {
        "signal": signal.get("asof_date"),
        "paper": latest.get("session_date"),
        "history": history.get("updated_session"),
        "risk": period.get("end"),
    }
    dates = {key: parse_date(val, key, issues) for key, val in raw.items()}
    for key, day in dates.items():
        if day is None:
            continue
        age = (today-day).days
        if age < 0:
            issues.append("FUTURE_PUBLISHED_DATE:" + key)
        elif age > MAX_AGE_DAYS:
            issues.append("STALE_PUBLISHED_DATE:" + key + ":" + str(age) + "d")
    if dates["signal"] is not None and dates["paper"] is not None:
        if dates["signal"] != dates["paper"]:
            issues.append("PUBLISHED_PAPER_ARCHIVE_STALE:paper=" + str(dates["paper"]) +
                          ":signal=" + str(dates["signal"]))
    for key in ("history", "risk"):
        if dates["signal"] is not None and dates[key] is not None:
            if dates["signal"] != dates[key]:
                issues.append("SOURCE_SESSION_MISMATCH:" + key)
    sessions = paper.get("sessions")
    if not isinstance(sessions, int) or isinstance(sessions, bool) or sessions < MIN_PAPER_SESSIONS:
        issues.append("PUBLISHED_PROSPECTIVE_PAPER_TOO_SHORT")
    if history.get("observed_ohlc_available") is not True:
        issues.append("OBSERVED_MARKET_DATA_NOT_VERIFIED")
    return {
        "kind": KIND,
        "checked_at_utc": now.astimezone(timezone.utc).isoformat(),
        "scope": "PUBLIC_GITHUB_ARCHIVE_ONLY_NOT_AUTHENTICATED_AWS_ST",
        "published_sessions": raw,
        "prospective_paper_sessions": sessions,
        "ready": not issues,
        "issues": issues,
        "broker_orders_authorized": False,
        "broker_fills_certified": False,
        "aws_st_signal_proven": False,
        "aws_st_paper_proven": False,
    }


ACTIVE_SCOPE = "PUBLIC_EPOCH5_MODELED_PAPER"
ACTIVE_KIND = "STOCKLENS_ACTIVE_PUBLICATION_READINESS_V1"


def assess_active(data, history, risk, model, now=None):
    from market_calendar import calendar, latest_provider_eligible_contract
    from infra.aws.epoch5_portal_reader import BOOK, FIRST, CONT
    from infra.aws.epoch5_public_model import KIND as MODEL_KIND

    now = now or datetime.now(timezone.utc)
    due = latest_provider_eligible_contract(now)["session"]
    cal = calendar()
    previous = cal.previous_session(due).date().isoformat()
    if (model.get("kind") != MODEL_KIND or model.get("book") != BOOK
            or model.get("first_session") != FIRST
            or model.get("broker_orders_authorized") is not False
            or model.get("broker_fills_observed") is not False):
        raise ValueError("UNEXPECTED_PUBLIC_MODEL")
    rows = {}
    for row in model["sessions"]:
        day = row["session_date"]
        if day in rows:
            raise ValueError("DUPLICATE_PUBLIC_SESSION")
        rows[day] = row

    receipts = []
    issues = []
    for day in (previous, due):
        row = rows.get(day, {})
        paper = row.get("paper") or {}
        prior = cal.previous_session(day).date().isoformat()
        if (row.get("paper_status") == "SHA_BOUND_SINGLE_VENDOR_MODELED"
                and paper.get("continuity_status") == CONT
                and (paper.get("execution_signal") or {}).get("session_date") == prior):
            receipts.append(day)
        else:
            issues.append("ACTIVE_RECEIPT_MISSING_OR_INVALID:" + day)
    if (rows.get(due, {}).get("signal") or {}).get("session_date") != due:
        issues.append("ACTIVE_SIGNAL_MISSING:" + due)
    if data.get("signal", {}).get("asof_date") != due:
        issues.append("PUBLISHED_SIGNAL_NOT_DUE_SESSION:" + due)

    # Reuse the common signal, history, risk and Paper publication checks.
    current = {"sessions": len(receipts), "latest": {"session_date": max(receipts, default=None)}}
    report = assess({**data, "paper": current}, history, risk, now)
    report["issues"].extend(issues)
    report.update(kind=ACTIVE_KIND, scope=ACTIVE_SCOPE, ready=not report["issues"],
                  expected_session=due, checked_receipt_sessions=receipts,
                  archived_paper_session=data.get("paper", {}).get("latest", {}).get("session_date"))
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("docs/data.json"))
    parser.add_argument("--history", type=Path, default=Path("docs/portal-history.json"))
    parser.add_argument("--risk", type=Path, default=Path("docs/observed_tqqq_risk_audit.json"))
    parser.add_argument("--summary", type=Path, help="Write an Actions job summary file")
    parser.add_argument("--active-model", type=Path, help="Public dashboard model response to verify")
    args = parser.parse_args()
    try:
        inputs = (
            json.loads(args.data.read_text(encoding="utf-8")),
            json.loads(args.history.read_text(encoding="utf-8")),
            json.loads(args.risk.read_text(encoding="utf-8")),
        )
        report = (assess_active(*inputs, json.loads(args.active_model.read_text(encoding="utf-8")))
                  if args.active_model else assess(*inputs))
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        report = {
            "kind": ACTIVE_KIND if args.active_model else KIND,
            "scope": ACTIVE_SCOPE if args.active_model else "PUBLIC_GITHUB_ARCHIVE_ONLY_NOT_AUTHENTICATED_AWS_ST",
            "ready": False,
            "issues": ["READINESS_INPUT_INVALID:" + type(exc).__name__],
            "broker_orders_authorized": False,
            "broker_fills_certified": False,
            "aws_st_signal_proven": False,
            "aws_st_paper_proven": False,
        }
    print(json.dumps(report, sort_keys=True, ensure_ascii=False))
    if args.summary:
        body = [
            "### Published GitHub Paper operational readiness",
            "",
            "**" + ("PASS" if report["ready"] else "BLOCKED") + "** — " + report["scope"] + ";",
            "not AWS ST Signal/Paper evidence or brokerage execution.",
            "",
        ]
        for issue in report["issues"]:
            body.append("- " + issue)
        if not report["issues"]:
            body.append("- Source dates match and the modeled Paper history is sufficiently long")
        body.append("")
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text("\n".join(body), encoding="utf-8")
    if report["ready"]:
        print("GITHUB_PUBLICATION_READINESS_PASS_NOT_AWS_ST_NOT_BROKER")
        return 0
    print("GITHUB_PUBLICATION_READINESS_BLOCKED:" + ",".join(report["issues"]))
    return 2


if __name__ == "__main__":
    sys.exit(main())

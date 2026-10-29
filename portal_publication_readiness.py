#!/usr/bin/env python3
"""Fail-closed published GitHub Paper freshness gate, NOT an AWS ST audit.

Browser passing means UI renders correctly, never that historical Paper is
current. This job separately gates paper-vs-signal, market history and risk.
No network, AWS changes, synthetic backfills, or broker authorizations.
"""
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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", type=Path, default=Path("docs/data.json"))
    parser.add_argument("--history", type=Path, default=Path("docs/portal-history.json"))
    parser.add_argument("--risk", type=Path, default=Path("docs/observed_tqqq_risk_audit.json"))
    parser.add_argument("--summary", type=Path, help="Write an Actions job summary file")
    args = parser.parse_args()
    try:
        report = assess(
            json.loads(args.data.read_text(encoding="utf-8")),
            json.loads(args.history.read_text(encoding="utf-8")),
            json.loads(args.risk.read_text(encoding="utf-8")),
        )
    except (ValueError, OSError, TypeError) as exc:
        report = {
            "kind": KIND,
            "scope": "PUBLIC_GITHUB_ARCHIVE_ONLY_NOT_AUTHENTICATED_AWS_ST",
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
            "**" + ("PASS" if report["ready"] else "BLOCKED") + "** — public static publication only;",
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

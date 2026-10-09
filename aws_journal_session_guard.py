"""NYSE-calendar gate for read-only AWS archival verification.

The AWS schedule executes Tue-Sat in UTC to inspect the preceding NY local day.
An archive is expected ONLY when that preceding date was an XNYS session.
This guard must fail closed if calendar data cannot be loaded. Skipping verification
on holidays is not evidence that the AWS EventBridge rules are enabled or healthy.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")


def evaluate(when: datetime, calendar=None) -> dict:
    if when.tzinfo is None:
        raise ValueError("TIME_MUST_BE_TIMEZONE_AWARE")
    import exchange_calendars as xcals
    cal = calendar if calendar is not None else xcals.get_calendar("XNYS")
    ny = when.astimezone(NY)
    candidate = (ny.date() - timedelta(days=1)).isoformat()
    # exchange_calendars.is_session also checks exceptional closures in its
    # published historical schedule; do not replace with weekday logic.
    required = bool(cal.is_session(candidate))
    return {
        "status": "ARCHIVE_EXPECTED" if required else "NO_XNYS_SESSION_NO_ARCHIVE_EXPECTED",
        "expected": required,
        "session": candidate,
        "ny_checked_at": ny.isoformat(),
        "exchange_calendar": "XNYS",
        "historical_venue_outage_detection_proven": False,
        "eventbridge_rule_enabled_verified": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--at-utc", help="UTC ISO 8601 for explicit testing")
    parser.add_argument("--github-output", help="GitHub Actions output path")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.at_utc.replace("Z", "+00:00")) if args.at_utc else datetime.now(timezone.utc)
    result = evaluate(now)
    if args.github_output:
        path = Path(args.github_output)
        with path.open("a", encoding="utf-8") as out:
            out.write("required=" + str(result["expected"]).lower() + "\n")
            out.write("session=" + result["session"] + "\n")
            out.write("verdict=" + result["status"] + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()

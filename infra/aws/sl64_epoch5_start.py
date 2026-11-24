"""Select and pin one prospective ST book, verify its source, then stage and arm it."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path

import boto3
import exchange_calendars as xcals


def next_open_session(now):
    calendar = xcals.get_calendar("XNYS")
    day = calendar.date_to_session(now.date().isoformat(), direction="next")
    if calendar.session_open(day).to_pydatetime() <= now:
        day = calendar.next_session(day)
    return day.date().isoformat()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--activate-st", action="store_true")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    sdk = boto3.Session(region_name="eu-central-1")
    clients = {name: sdk.client(name) for name in
               ("sts", "s3", "lambda", "cloudformation", "events", "cloudwatch")}
    if clients["sts"].get_caller_identity()["Account"] != "634740393398":
        raise RuntimeError("WRONG_AWS_ACCOUNT")
    first = next_open_session(now)
    function = "stocklens-st-epoch5-paper-dark"
    try:
        cfg = clients["lambda"].get_function_configuration(FunctionName=function)
    except clients["lambda"].exceptions.ResourceNotFoundException:
        cfg = None
    if cfg is not None:
        settings = cfg["Environment"]["Variables"]
        first = settings.get("STOCKLENS_ST_FIRST_SESSION", "2026-11-20")

    os.environ["STOCKLENS_ST_FIRST_SESSION"] = first
    from infra.aws import sl64_epoch5_automated_release as release
    from infra.aws import sl64_epoch5_preopen as approval
    from infra.aws import sl64_epoch5_stage_dark_deploy as stage

    repo = Path(__file__).resolve().parents[2]
    release.legacy_approval.inspect(clients)
    if cfg is not None and settings.get("STOCKLENS_EPOCH5_WRITE_ENABLED") == "true":
        for name, fn in ((release.PAPER_RULE, release.FUNCTION), (release.WATCH_RULE, release.WATCHDOG)):
            rule = clients["events"].describe_rule(Name=name)
            targets = clients["events"].list_targets_by_rule(Rule=name)["Targets"]
            expected = f"arn:aws:lambda:{stage.REGION}:{stage.ACCOUNT}:function:{fn}"
            if rule["State"] != "ENABLED" or [target["Arn"] for target in targets] != [expected]:
                raise RuntimeError(f"EXISTING_ST_SCHEDULE_OR_TARGET_CHANGED: {name}")
        release._invoke(clients, function, "STAGING_EPOCH5_READ_ONLY_PREFLIGHT",
                        "EPOCH5_ARMED_READINESS_S3_READ_ONLY")
        print(f"ST schedules and startup source verified for {first}; daily receipts require the watchdog.")
        return 0

    check = approval.preflight(clients["sts"], clients["s3"], now=now)
    print(json.dumps({"first_session": first, "prior_signal": check["source_key"],
                      "opening_utc": check["opening_utc"]}), flush=True)
    if not args.activate_st:
        return 0
    if check["preopen_approval_new_write_eligible"]:
        approval.approve(clients["sts"], clients["s3"], now=datetime.now(timezone.utc), enabled=True)
    # A retry during the session must already have an approval saved before its open.
    stack = stage._existing(clients["cloudformation"])
    if stack is None or stack["StackStatus"] == "CREATE_COMPLETE":
        result, rc = stage.execute(clients, repo, stage=True)
        print(json.dumps(result), flush=True)
        if rc:
            return rc
    result, rc = release.release(clients, repo, execute=True)
    print(json.dumps(result), flush=True)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())

"""Calendar-aware, read-only session watchdog for the AWS staging candidate.

Replaces a fixed "no invocation in 26h" deadman, which is wrong for XNYS: weekends,
holidays (Good Friday, Thanksgiving...), early closes and a deliberately DISABLED
scheduler all produce legitimate silence. Instead, for each recent XNYS session whose
accounting deadline (next session's open) has passed, a continuity record must exist.

It also alarms when the scheduler is in an unexpected state -- in staging the expected
state is DISABLED, so an unauthorized ENABLE is itself an alert.

Runs hourly every day (its own fixed-period deadman is therefore valid). Read-only on
S3/EventBridge; writes only CloudWatch metrics. No broker access.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os

from infra.aws import session_continuity as sc
from infra.aws.independent_signal_monitor import due_signal_sessions

NAMESPACE = "StockLens/IndependentStaging"
MAX_MONITORED_SESSIONS = 400


def resolve_paper_monitoring_start(configured: str | None, genesis) -> str | None:
    """The immutable S3 genesis starts monitoring automatically after bootstrap.

    A blank CloudFormation parameter must NOT silently disable Paper monitoring
    after an operator has established a real staging book.
    """
    if configured:
        return configured
    if genesis is None:
        return None
    if (not isinstance(genesis, dict) or
            genesis.get("schema") != sc.GENESIS_SCHEMA or
            genesis.get("book") != sc.BOOK or
            not isinstance(genesis.get("bootstrap_session"), str)):
        return "INVALID_DURABLE_GENESIS"
    return genesis["bootstrap_session"]  # beyond this, archive/checkpoint and move MonitoringStartSession


def due_sessions(now: datetime, monitoring_start: str) -> list[str]:
    """ALL sessions since monitoring_start whose accounting deadline has passed.
    No sliding window: an unresolved old hole keeps alarming until it is resolved."""
    import exchange_calendars as xcals
    if now.tzinfo is None:
        raise ValueError("WATCHDOG_CLOCK_MUST_BE_AWARE")
    cal = xcals.get_calendar("XNYS")
    now = now.astimezone(timezone.utc)
    end = cal.date_to_session(now.date().isoformat(), direction="previous").date().isoformat()
    start = cal.date_to_session(monitoring_start, direction="next").date().isoformat()
    if start > end:
        return []
    sessions = [d.date().isoformat() for d in cal.sessions_in_range(start, end)]
    return [x for x in sessions if sc.accounting_deadline_utc(x) <= now]


def inspect(*, now: datetime, rule_state: str | None, expected_rule_state: str,
            monitoring_start: str | None, read_record, read_receipt_sha=lambda s: None,
            read_last_modified=None, read_genesis=None, book: str = sc.BOOK,
            signal_rule_state: str | None = None, signal_activation_at: datetime | None = None,
            read_signal_saved_at=None, paper_rule_state: str | None = None) -> dict:
    """read_record(session) -> dict | None; read_receipt_sha(session) -> sha | None;
    read_last_modified(key) -> aware datetime | None (genuine S3 server time).

    read_genesis() -> dict | None: the durable S3 book genesis object.

    Paper completeness monitoring is ON whenever MonitoringStartSession is set and is
    INDEPENDENT of the trading scheduler: a deliberately DISABLED orchestrator (manual
    staging runs) must still have every completed session's evidence checked. The chain
    is anchored to the real S3 genesis: MonitoringStartSession must equal its bootstrap
    session, and the first record must bind to it by hash. Every FAIL_CLOSED is
    reflected in an alarmed metric."""
    failures, missed, halted, invalid = [], [], [], {}
    config_errors = []
    if expected_rule_state not in ("ENABLED", "DISABLED"):
        config_errors.append("EXPECTED_SCHEDULER_STATE_INVALID")
    mismatch = rule_state != expected_rule_state
    if mismatch:
        failures.append(f"SCHEDULER_STATE_UNEXPECTED:{rule_state}!={expected_rule_state}")
    if rule_state == "ENABLED" and not monitoring_start:
        config_errors.append("MONITORING_START_SESSION_UNSET_WHILE_ENABLED")
    if paper_rule_state is not None:
        if paper_rule_state not in ("ENABLED", "DISABLED"):
            config_errors.append("PAPER_ONLY_RULE_UNREADABLE:" + str(paper_rule_state))
        elif paper_rule_state == "ENABLED" and not monitoring_start:
            config_errors.append("AUTOMATED_PAPER_ENABLED_WITHOUT_GENESIS")
    checking = bool(monitoring_start)            # decoupled from the scheduler state
    genesis = None
    if checking:
        try:
            genesis = read_genesis() if read_genesis is not None else None
        except Exception as exc:
            config_errors.append("GENESIS_READ_FAILED:" + type(exc).__name__)
        if genesis is None:
            config_errors.append("GENESIS_UNVERIFIED")
        elif genesis.get("bootstrap_session") != monitoring_start:
            config_errors.append("MONITORING_START_IS_NOT_BOOK_GENESIS")
    if checking:
        try:
            due = due_sessions(now, monitoring_start)
        except Exception as exc:
            due = []
            config_errors.append("MONITORING_START_INVALID:" + type(exc).__name__)
        if len(due) > MAX_MONITORED_SESSIONS:
            config_errors.append(f"MONITORED_RANGE_TOO_LONG:{len(due)}")
            due = []
        prev_rec = None
        for session in due:
            try:
                rec = read_record(session)
                receipt_sha = read_receipt_sha(session) if rec is not None else None
            except Exception as exc:
                config_errors.append(f"READ_FAILED:{session}:{type(exc).__name__}")
                prev_rec = None
                continue
            if rec is None:
                missed.append(session)
                prev_rec = None
                continue
            kw = {}
            if read_last_modified is not None:
                try:
                    kw = dict(
                        check_s3_times=True,
                        receipt_saved_at=read_last_modified(f"paper/sessions/{session}.json"),
                        signal_saved_at=read_last_modified(
                            f"signals/{sc.previous_session(session)}.json"))
                except Exception as exc:
                    config_errors.append(f"READ_FAILED:{session}:{type(exc).__name__}")
                    prev_rec = None
                    continue
            errs = sc.validate_record(rec, session=session, book=book,
                                      previous=prev_rec, receipt_sha256=receipt_sha, **kw)
            if session == monitoring_start:
                errs = errs + sc.validate_genesis(genesis, rec, book=book)
            if errs:
                invalid[session] = errs
            elif rec.get("status") == sc.MISSED:
                halted.append(session)
            prev_rec = rec
    # Signal-only has an independent S3-server-timed activation anchor. Do not
    # treat arbitrary pre-activation history as missed automatic executions.
    signal_missing, signal_late = [], []
    # Independent operational visibility: retain lifetime fail-closed incident
    # alarms while still reporting whether the *latest due* signal is healthy.
    # This never clears or overrides any missing/late historic evidence.
    latest_due_signal_session = None
    latest_due_signal_status = "NOT_DUE"
    signal_session_statuses = {}
    if signal_rule_state is not None:
        if signal_rule_state not in ("ENABLED", "DISABLED"):
            config_errors.append("SIGNAL_RULE_UNREADABLE:" + str(signal_rule_state))
        elif signal_rule_state == "ENABLED" and signal_activation_at is None:
            config_errors.append("SIGNAL_RULE_ENABLED_WITHOUT_ACTIVATION_ANCHOR")
        elif signal_rule_state == "DISABLED" and signal_activation_at is not None:
            config_errors.append("SIGNAL_RULE_DISABLED_AFTER_ACTIVATION")
        if signal_rule_state == "ENABLED" and signal_activation_at is not None:
            if read_signal_saved_at is None:
                config_errors.append("SIGNAL_RECEIPT_READER_MISSING")
            else:
                try:
                    due = due_signal_sessions(now, signal_activation_at)
                except Exception as exc:
                    config_errors.append("SIGNAL_CALENDAR_ERROR:" + type(exc).__name__)
                    due = []
                if due:
                    latest_due_signal_session = due[-1][0]
                for session, deadline in due:
                    try:
                        saved = read_signal_saved_at(session)
                    except Exception as exc:
                        config_errors.append("SIGNAL_S3_READ_ERROR:" + session + ":" + type(exc).__name__)
                        signal_session_statuses[session] = "READ_ERROR"
                        continue
                    if saved is None:
                        signal_missing.append(session)
                        signal_session_statuses[session] = "MISSING"
                    elif saved.tzinfo is None or saved.astimezone(timezone.utc) > deadline:
                        signal_late.append(session)
                        signal_session_statuses[session] = "LATE"
                    else:
                        signal_session_statuses[session] = "ON_TIME"
                if latest_due_signal_session is not None:
                    latest_due_signal_status = signal_session_statuses[latest_due_signal_session]
    failures += ["MISSING_SCHEDULED_SIGNAL:" + d for d in signal_missing]
    failures += ["LATE_SCHEDULED_SIGNAL:" + d for d in signal_late]
    failures += ["SESSION_WITHOUT_CONTINUITY_RECORD:" + x for x in missed]
    failures += ["BOOK_HALTED_AT:" + x for x in halted]
    failures += [f"INVALID_CONTINUITY_RECORD:{k}:{','.join(v)}" for k, v in invalid.items()]
    failures += ["CONFIGURATION:" + e for e in config_errors]
    mode = "CHECKING" if checking else "NOT_CONFIGURED_NO_BOOK_MONITORING"
    return {
        "checked_utc": now.astimezone(timezone.utc).isoformat(),
        "mode": mode,
        "missing_scheduled_signals": signal_missing,
        "late_scheduled_signals": signal_late,
        "latest_due_signal_session": latest_due_signal_session,
        "latest_due_signal_status": latest_due_signal_status,
        "historical_signal_incidents": [
            {"session": day, "status": signal_session_statuses[day]}
            for day in sorted(signal_session_statuses)
            if day != latest_due_signal_session
            and signal_session_statuses[day] != "ON_TIME"
        ],
        "missed_sessions": missed,
        "halted_sessions": halted,
        "invalid_records": invalid,
        "metrics": {
            "MissingOrLateScheduledSignals": len(signal_missing) + len(signal_late),
            "MissedSessions": len(missed),
            "BookHalted": len(halted),
            "InvalidReceipts": len(invalid),
            "ConfigurationError": len(config_errors),
            "SchedulerStateMismatch": int(mismatch),
            "WatchdogFailClosed": int(bool(failures)),
            "WatchdogHeartbeat": 1,
        },
        "failures": failures,
        "status": "FAIL_CLOSED" if failures else "PASS",
        "broker_execution_authorized": False,
    }


def _import_smoke():
    import importlib
    for package in ("exchange_calendars", "boto3", "infra.aws.session_continuity",
                    "infra.aws.independent_paper"):
        importlib.import_module(package)
    for var in ("STOCKLENS_DATA_BUCKET", "ORCHESTRATOR_RULE", "SIGNAL_ONLY_RULE", "PAPER_ONLY_RULE", "EXPECTED_SCHEDULER_STATE"):
        if not os.environ.get(var):
            raise RuntimeError("STAGING_ENV_MISSING:" + var)
    return {"status": "STAGING_IMPORT_OK", "component": "watchdog",
            "broker_actions": False, "market_data_written": False}


def handler(event, context):
    if (event or {}).get("mode") == "STAGING_IMPORT_SMOKE":
        return _import_smoke()
    import boto3
    s3, events, cw = boto3.client("s3"), boto3.client("events"), boto3.client("cloudwatch")
    bucket = os.environ["STOCKLENS_DATA_BUCKET"]
    try:
        rule_state = events.describe_rule(Name=os.environ["ORCHESTRATOR_RULE"]).get("State")
    except Exception as exc:  # unreadable scheduler is itself an alert
        rule_state = "UNREADABLE:" + type(exc).__name__

    try:
        signal_rule_state = events.describe_rule(Name=os.environ["SIGNAL_ONLY_RULE"]).get("State")
    except Exception as exc:
        signal_rule_state = "UNREADABLE:" + type(exc).__name__

    try:
        paper_rule_state = events.describe_rule(Name=os.environ["PAPER_ONLY_RULE"]).get("State")
    except Exception as exc:
        paper_rule_state = "UNREADABLE:" + type(exc).__name__

    def read_signal_activation():
        """Read a strictly formatted immutable S3 marker and its SERVER timestamp."""
        try:
            obj = s3.get_object(Bucket=bucket, Key="monitoring/signal-only-activation.json")
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404", "NotFound"):
                return None
            raise
        marker = json.loads(obj["Body"].read(4096))
        if marker != {"schema": "STOCKLENS_STAGING_SIGNAL_MONITOR_V1"}:
            raise ValueError("INVALID_SIGNAL_ACTIVATION_MARKER")
        if not obj.get("VersionId") or obj["VersionId"] == "null":
            raise ValueError("SIGNAL_ACTIVATION_MISSING_S3_VERSION")
        ts = obj.get("LastModified")
        if ts is None or ts.tzinfo is None:
            raise ValueError("SIGNAL_ACTIVATION_MISSING_S3_SERVER_TIME")
        return ts

    def read_record(session):
        try:
            obj = s3.get_object(Bucket=bucket, Key=f"paper/continuity/{session}.json")
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404", "NotFound"):
                return None
            raise
        return json.loads(obj["Body"].read(2_000_000))

    from infra.aws.independent_paper import s3_object_sha256_and_time, GENESIS_KEY

    def read_receipt_sha(session):
        return s3_object_sha256_and_time(s3, bucket, f"paper/sessions/{session}.json")[0]

    def read_genesis():
        try:
            obj = s3.get_object(Bucket=bucket, Key=GENESIS_KEY)
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404", "NotFound"):
                return None
            raise
        return json.loads(obj["Body"].read(100_000))

    def read_last_modified(key):
        try:
            return s3.head_object(Bucket=bucket, Key=key)["LastModified"]
        except Exception as exc:
            code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if code in ("NoSuchKey", "404", "NotFound"):
                return None
            raise

    try:
        signal_activation_at = read_signal_activation()
    except Exception as exc:
        # Corrupt/unreadable anchor always alerts rather than silently resetting.
        signal_activation_at = None
        signal_rule_state = "UNREADABLE_ANCHOR:" + type(exc).__name__

    configured_start = os.environ.get("MONITORING_START_SESSION") or None
    # Inspect the book even before an operator updates the optional CF
    # MonitoringStartSession parameter. Invalid/unreadable genesis is an alarm,
    # not a reason to quietly stop checking the Paper account.
    try:
        durable_genesis = read_genesis()
    except Exception as exc:
        durable_genesis = None
        configured_start = configured_start or "INVALID_DURABLE_GENESIS"
        genesis_reader = lambda error=exc: (_ for _ in ()).throw(error)
    else:
        genesis_reader = lambda: durable_genesis
    monitoring_start = resolve_paper_monitoring_start(configured_start, durable_genesis)

    result = inspect(now=datetime.now(timezone.utc), rule_state=rule_state,
                     expected_rule_state=os.environ["EXPECTED_SCHEDULER_STATE"],
                     monitoring_start=monitoring_start,
                     read_record=read_record, read_receipt_sha=read_receipt_sha,
                     read_last_modified=read_last_modified, read_genesis=genesis_reader,
                     paper_rule_state=paper_rule_state,
                     signal_rule_state=signal_rule_state,
                     signal_activation_at=signal_activation_at,
                     read_signal_saved_at=lambda day: read_last_modified(f"signals/{day}.json"))
    cw.put_metric_data(Namespace=NAMESPACE, MetricData=[
        {"MetricName": k, "Value": float(v), "Unit": "Count"} for k, v in result["metrics"].items()])
    print(json.dumps(result, sort_keys=True))
    return result

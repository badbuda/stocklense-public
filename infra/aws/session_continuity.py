"""Append-only, hash-chained session continuity journal for the AWS staging Paper book.

Every XNYS session after the explicit bootstrap gets exactly one immutable record at
``paper/continuity/{session}.json`` -- including failures. Nothing here creates orders,
fills, signals or timestamps; it classifies evidence that already exists.

Statuses (the only four allowed):

ON_TIME_QUALIFIED
    The decision signal for the session was archived in S3 (server LastModified, not the
    self-reported generated_at) before 09:30 NY of the execution session, AND the paper
    receipt was written before the next session's open.
LATE_WITH_CONTEMPORANEOUS_EVIDENCE
    Signal archival before the open is proven by S3, but the paper accounting ran after the
    deadline (catch-up). Decision timing is valid forward evidence; the operational SLO was
    missed and is recorded as such.
RECONSTRUCTED_ACCOUNTING_ONLY
    Accounting was completed, but pre-open signal archival is NOT proven by S3. Never forward
    evidence; it breaks the qualification epoch.
MISSED_UNRECOVERABLE
    No reliable accounting was possible (signal never archived, or observed execution bars
    unavailable). The book is HALTED: later sessions are refused until a human resumes it.

Qualification is never retroactive: ``epoch`` increments on the first qualifying record
after any non-qualifying one, and streaks are only counted inside the current epoch.
"""
from __future__ import annotations

from datetime import date, datetime, time, timezone
import hashlib
import json
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")

ON_TIME = "ON_TIME_QUALIFIED"
LATE = "LATE_WITH_CONTEMPORANEOUS_EVIDENCE"
RECONSTRUCTED = "RECONSTRUCTED_ACCOUNTING_ONLY"
MISSED = "MISSED_UNRECOVERABLE"
STATUSES = (ON_TIME, LATE, RECONSTRUCTED, MISSED)
FORWARD_EVIDENCE = (ON_TIME, LATE)
SCHEMA = "STOCKLENS_SESSION_CONTINUITY_V1"
MAX_CATCHUP_SESSIONS = 5
BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK"


def canonical(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _cal():
    import exchange_calendars as xcals
    return xcals.get_calendar("XNYS")


def _aware(ts: datetime | None, name: str) -> datetime | None:
    if ts is None:
        return None
    if ts.tzinfo is None:
        raise ValueError("NAIVE_TIMESTAMP:" + name)
    return ts.astimezone(timezone.utc)


def session_open_utc(session: str) -> datetime:
    """Actual XNYS open for the session (handles DST; opens are 09:30 NY)."""
    cal = _cal()
    if not cal.is_session(session):
        raise ValueError("NOT_XNYS_SESSION:" + session)
    return cal.session_open(session).to_pydatetime().astimezone(timezone.utc)


def session_close_utc(session: str) -> datetime:
    """Actual close, including early closes (e.g. 13:00 NY day after Thanksgiving)."""
    cal = _cal()
    if not cal.is_session(session):
        raise ValueError("NOT_XNYS_SESSION:" + session)
    return cal.session_close(session).to_pydatetime().astimezone(timezone.utc)


def next_session(session: str) -> str:
    return _cal().next_session(session).date().isoformat()


def previous_session(session: str) -> str:
    return _cal().previous_session(session).date().isoformat()


def accounting_deadline_utc(session: str) -> datetime:
    """Paper for session S must exist before the next session's open."""
    return session_open_utc(next_session(session))


def classify(*, session: str, signal_archived_at: datetime | None,
             processed_at: datetime | None, accounting_completed: bool) -> str:
    """Pure classification, fail-closed on its own (does not rely on callers).

    ``signal_archived_at``: S3 server LastModified of the decision signal (the prior
    session's close signal), or None if unattested/missing.
    ``processed_at``: S3 server LastModified of the *saved paper receipt* -- the
    moment accounting was durably completed, not when the Lambda started.
    """
    signal_archived_at = _aware(signal_archived_at, "signal_archived_at")
    processed_at = _aware(processed_at, "processed_at")
    if not accounting_completed:
        return MISSED
    if processed_at is None:
        raise ValueError("PROCESSED_AT_REQUIRED_FOR_COMPLETED_ACCOUNTING")
    # Accounting saved before this session's (possibly early) close cannot be based on
    # the completed session: never forward evidence.
    if processed_at < session_close_utc(session):
        return RECONSTRUCTED
    # The decision signal must be archived after the prior session closed (otherwise it
    # could not have used the completed close) and before this session's open.
    pre_open = (signal_archived_at is not None
                and session_close_utc(previous_session(session)) <= signal_archived_at
                < session_open_utc(session))
    if not pre_open:
        return RECONSTRUCTED
    if processed_at < accounting_deadline_utc(session):
        return ON_TIME
    return LATE


def derive_counters(previous: dict | None, status: str) -> tuple[int, int, dict]:
    """The ONLY definition of epoch / streak / totals. Validation recomputes these from
    the predecessor; stored values are never trusted as inputs."""
    if previous is None:
        epoch, streak, totals, prev_qualifying = 1, 0, {s: 0 for s in STATUSES}, True
    else:
        epoch = previous["epoch"]
        streak = previous["qualified_streak_in_epoch"]
        totals = {s: previous["totals"][s] for s in STATUSES}
        prev_qualifying = previous["status"] in FORWARD_EVIDENCE
    qualifying = status in FORWARD_EVIDENCE
    if qualifying and not prev_qualifying:
        epoch, streak = epoch + 1, 0
    streak = streak + 1 if qualifying else 0
    totals = dict(totals)
    totals[status] += 1
    return epoch, streak, totals


def build_record(*, session: str, status: str, previous_record: dict | None,
                 previous_record_sha256: str | None, processed_at: datetime,
                 signal_archived_at: datetime | None, reason: str | None = None,
                 evidence: dict | None = None, book: str) -> dict:
    """Next immutable continuity record. Enforces strict session adjacency so a gap
    can never be skipped silently: the record for S must chain to the record for S-1."""
    if status not in STATUSES:
        raise ValueError("UNKNOWN_CONTINUITY_STATUS")
    if status == MISSED and not reason:
        raise ValueError("MISSED_SESSION_REASON_REQUIRED")
    processed_at = _aware(processed_at, "processed_at")
    if previous_record is not None:
        if hashlib.sha256(canonical(previous_record)).hexdigest() != previous_record_sha256:
            raise ValueError("CONTINUITY_PREVIOUS_SHA_MISMATCH")
        if previous_record.get("book") != book:
            raise ValueError("CONTINUITY_BOOK_MISMATCH")
        if previous_record["session"] != previous_session(session):
            raise ValueError("CONTINUITY_GAP_NOT_RECORDED")
        if previous_record["status"] == MISSED and not (evidence or {}).get("human_resume_ticket"):
            raise ValueError("BOOK_HALTED_AFTER_MISSED_SESSION_HUMAN_RESUME_REQUIRED")
    elif previous_record_sha256 is not None:
        raise ValueError("ORPHAN_PREVIOUS_SHA")
    epoch, streak, totals = derive_counters(previous_record, status)
    qualifying = status in FORWARD_EVIDENCE
    return {
        "schema": SCHEMA,
        "book": book,
        "session": session,
        "status": status,
        "forward_evidence": qualifying,
        "operational_sla_met": status == ON_TIME,
        "epoch": epoch,
        "qualified_streak_in_epoch": streak,
        "totals": totals,
        "previous_record_sha256": previous_record_sha256,
        "processed_at_utc": processed_at.isoformat(),
        "signal_archived_at_utc": (_aware(signal_archived_at, "signal_archived_at").isoformat()
                                   if signal_archived_at else None),
        "timing_attestation": "S3_SERVER_LAST_MODIFIED" if signal_archived_at else "NONE",
        "reason": reason,
        "evidence": evidence or {},
        "book_halted": status == MISSED,
        "broker_orders": False,
        "broker_fills": False,
    }


def plan_catchup(*, last_recorded_session: str, target_session: str,
                 max_sessions: int = MAX_CATCHUP_SESSIONS) -> list[str]:
    """Sessions strictly after last_recorded_session up to target, in order.
    Refuses (fail-closed) beyond the bounded horizon so a long outage needs a human."""
    cal = _cal()
    if not cal.is_session(target_session) or not cal.is_session(last_recorded_session):
        raise ValueError("NOT_XNYS_SESSION")
    if last_recorded_session >= target_session:
        return []
    out = [d.date().isoformat() for d in cal.sessions_in_range(last_recorded_session, target_session)][1:]
    if len(out) > max_sessions:
        raise RuntimeError(f"CATCHUP_HORIZON_EXCEEDED:{len(out)}>{max_sessions}_HUMAN_REVIEW_REQUIRED")
    return out


_HEX = set("0123456789abcdef")


def _is_sha(v) -> bool:
    return isinstance(v, str) and len(v) == 64 and set(v) <= _HEX


RECORD_FIELDS = frozenset({
    "schema", "book", "session", "status", "forward_evidence", "operational_sla_met",
    "epoch", "qualified_streak_in_epoch", "totals", "previous_record_sha256",
    "processed_at_utc", "signal_archived_at_utc", "timing_attestation", "reason",
    "evidence", "book_halted", "broker_orders", "broker_fills"})


def _parse_ts(v):
    if not isinstance(v, str):
        return None
    try:
        ts = datetime.fromisoformat(v.replace("Z", "+00:00"))
    except ValueError:
        return None
    return ts.astimezone(timezone.utc) if ts.tzinfo else None


def validate_record(rec, *, session: str, book: str = BOOK,
                    previous: dict | None = None, receipt_sha256: str | None = None,
                    receipt_saved_at: datetime | None = None,
                    signal_saved_at: datetime | None = None,
                    check_s3_times: bool = False) -> list[str]:
    """Full validation; returns error codes ([] = valid). Nothing stored is trusted:

    - counters (epoch/streak/totals) are recomputed from ``previous`` via derive_counters;
    - a record with a predecessor hash MUST be validated against that predecessor, which
      must be the immediately preceding XNYS session; only genesis may omit it;
    - status is recomputed with classify() from the recorded times;
    - with check_s3_times, the recorded times must equal the genuine S3 LastModified of
      the stored receipt and of the prior session's archived signal.
    The caller is responsible for having validated ``previous`` itself (chain induction).
    """
    if not isinstance(rec, dict):
        return ["NOT_AN_OBJECT"]
    errs = []
    if set(rec) != RECORD_FIELDS:
        errs.append("FIELD_SET")
    if rec.get("schema") != SCHEMA:
        errs.append("SCHEMA")
    status = rec.get("status")
    if status not in STATUSES:
        return errs + ["STATUS"]
    if rec.get("session") != session:
        errs.append("SESSION_MISMATCH")
    if rec.get("book") != book:
        errs.append("BOOK_MISMATCH")
    if rec.get("forward_evidence") is not (status in FORWARD_EVIDENCE):
        errs.append("FORWARD_EVIDENCE_FLAG")
    if rec.get("book_halted") is not (status == MISSED):
        errs.append("HALTED_FLAG")
    if rec.get("operational_sla_met") is not (status == ON_TIME):
        errs.append("SLA_FLAG")
    if rec.get("broker_orders") is not False or rec.get("broker_fills") is not False:
        errs.append("BROKER_FLAGS")
    evidence = rec.get("evidence") if isinstance(rec.get("evidence"), dict) else None
    if evidence is None:
        errs.append("EVIDENCE_FORMAT")
        evidence = {}

    # ---- chain anchoring and adjacency ----
    prev_sha = rec.get("previous_record_sha256")
    if previous is None:
        if prev_sha is not None:
            errs.append("PREDECESSOR_UNVERIFIED")
            return errs  # counters cannot be recomputed without the predecessor
    else:
        if prev_sha != hashlib.sha256(canonical(previous)).hexdigest():
            errs.append("CHAIN_BROKEN")
        try:
            adjacent = previous.get("session") == previous_session(session)
        except Exception:
            adjacent = False
        if not adjacent:
            errs.append("NONADJACENT_PREDECESSOR")
        if previous.get("book") != book:
            errs.append("PREDECESSOR_BOOK_MISMATCH")
        if previous.get("status") == MISSED and not evidence.get("human_resume_ticket"):
            errs.append("RESUMED_AFTER_MISSED_WITHOUT_TICKET")

    # ---- counters recomputed, never read ----
    try:
        epoch, streak, totals = derive_counters(previous, status)
    except Exception:
        errs.append("PREDECESSOR_COUNTERS_INVALID")
    else:
        if rec.get("epoch") != epoch or type(rec.get("epoch")) is not int:
            errs.append("DERIVED_EPOCH_MISMATCH")
        if rec.get("qualified_streak_in_epoch") != streak or type(rec.get("qualified_streak_in_epoch")) is not int:
            errs.append("DERIVED_STREAK_MISMATCH")
        if rec.get("totals") != totals:
            errs.append("DERIVED_TOTALS_MISMATCH")

    # ---- timing recomputed from recorded times ----
    processed = _parse_ts(rec.get("processed_at_utc"))
    signal_at = _parse_ts(rec.get("signal_archived_at_utc"))
    if processed is None:
        errs.append("PROCESSED_AT_FORMAT")
    if rec.get("signal_archived_at_utc") is not None and signal_at is None:
        errs.append("SIGNAL_AT_FORMAT")
    expected_attestation = "S3_SERVER_LAST_MODIFIED" if rec.get("signal_archived_at_utc") else "NONE"
    if rec.get("timing_attestation") != expected_attestation:
        errs.append("TIMING_ATTESTATION")
    if processed is not None:
        try:
            recomputed = classify(session=session, signal_archived_at=signal_at,
                                  processed_at=processed, accounting_completed=status != MISSED)
        except Exception:
            recomputed = None
        if recomputed != status:
            errs.append("CLASSIFICATION_INCONSISTENT")

    # ---- receipt and S3 server-time cross-checks ----
    if status == MISSED:
        if not rec.get("reason"):
            errs.append("MISSED_WITHOUT_REASON")
        if receipt_sha256 is not None:
            errs.append("MISSED_BUT_RECEIPT_EXISTS")
    else:
        if not _is_sha(evidence.get("paper_sha256")):
            errs.append("RECEIPT_SHA_MISSING")
        elif receipt_sha256 != evidence["paper_sha256"]:
            errs.append("RECEIPT_SHA_MISMATCH")
        if check_s3_times:
            if receipt_saved_at is None or processed is None or \
                    _aware(receipt_saved_at, "receipt_saved_at") != processed:
                errs.append("PROCESSED_AT_NOT_S3_RECEIPT_TIME")
            if signal_at is not None and (signal_saved_at is None or
                                          _aware(signal_saved_at, "signal_saved_at") != signal_at):
                errs.append("SIGNAL_TIME_NOT_S3_TIME")
    return errs


GENESIS_FIELDS = frozenset({"schema", "book", "bootstrap_session",
                            "receipt_sha256", "continuity_sha256"})
GENESIS_SCHEMA = "STOCKLENS_BOOK_GENESIS_V1"


def build_genesis(*, book: str, first_record: dict) -> dict:
    return {"schema": GENESIS_SCHEMA, "book": book,
            "bootstrap_session": first_record["session"],
            "receipt_sha256": first_record["evidence"]["paper_sha256"],
            "continuity_sha256": hashlib.sha256(canonical(first_record)).hexdigest()}


def validate_genesis(genesis, first_record, *, book: str = BOOK) -> list[str]:
    """The durable book genesis object must bind exactly to the chain's first record."""
    if not isinstance(genesis, dict):
        return ["GENESIS_MISSING"]
    errs = []
    if set(genesis) != GENESIS_FIELDS or genesis.get("schema") != GENESIS_SCHEMA:
        errs.append("GENESIS_FORMAT")
    if genesis.get("book") != book:
        errs.append("GENESIS_BOOK_MISMATCH")
    if not isinstance(first_record, dict):
        return errs + ["GENESIS_FIRST_RECORD_MISSING"]
    if first_record.get("session") != genesis.get("bootstrap_session"):
        errs.append("GENESIS_SESSION_MISMATCH")
    if first_record.get("previous_record_sha256") is not None:
        errs.append("GENESIS_FIRST_RECORD_HAS_PREDECESSOR")
    if (first_record.get("evidence") or {}).get("paper_sha256") != genesis.get("receipt_sha256"):
        errs.append("GENESIS_RECEIPT_MISMATCH")
    if hashlib.sha256(canonical(first_record)).hexdigest() != genesis.get("continuity_sha256"):
        errs.append("GENESIS_CONTINUITY_MISMATCH")
    return errs


def verify_chain(records: list[dict], *, book: str = BOOK) -> list[str]:
    """Validate a full chain from genesis (no S3 cross-checks). [] = valid."""
    errs, prev = [], None
    for rec in records:
        e = validate_record(rec, session=rec.get("session"), book=book, previous=prev,
                            receipt_sha256=(rec.get("evidence") or {}).get("paper_sha256"))
        errs += [f"{rec.get('session')}:{x}" for x in e]
        prev = rec
    return errs


def summarize(records: list[dict]) -> dict:
    """Forward-evidence summary RECOMPUTED from a chain verified from genesis.
    Stored counters are never read; an invalid chain raises."""
    if not records:
        return {"sessions": 0}
    errs = verify_chain(records, book=records[0].get("book"))
    if errs:
        raise ValueError("UNVERIFIED_CHAIN:" + ";".join(errs[:10]))
    prev = None
    on_time_streak = 0
    for rec in records:
        epoch, streak, totals = derive_counters(prev, rec["status"])
        prev = dict(rec, epoch=epoch, qualified_streak_in_epoch=streak, totals=totals)
        on_time_streak = on_time_streak + 1 if rec["status"] == ON_TIME else 0
    return {
        "sessions": len(records),
        "totals": totals,
        "current_epoch": epoch,
        # Decision-timing evidence: the decision existed (S3-attested) before the open.
        # ON_TIME and LATE both qualify here. This is NOT execution evidence.
        "decision_timing_streak_in_current_epoch": streak,
        "qualified_streak_in_current_epoch": streak,  # back-compat alias of the above
        # Operational streak: consecutive ON_TIME only (LATE breaks it).
        "on_time_streak": on_time_streak,
        # Execution evidence requires independently verified execution prices / fills
        # for 09:31/09:32. No such source exists yet, so nothing qualifies -- including
        # ON_TIME sessions whose fills are modelled from Yahoo 1-minute bars.
        "execution_qualified_sessions": 0,
        "execution_qualification": "BLOCKED_NO_INDEPENDENT_EXECUTION_SOURCE",
        "book_halted": records[-1]["status"] == MISSED,
        "forward_evidence_sessions_total": sum(r["status"] in FORWARD_EVIDENCE for r in records),
        "note": ("Recomputed from a verified chain. 63/252 EXECUTION gates must use "
                 "execution_qualified_sessions, never the decision-timing streak."),
    }

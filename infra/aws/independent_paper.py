"""AWS candidate prospective paper ledger, using unchanged frozen StockLens paper math.

At runtime the *existing* fetch_execution_market downloads observed raw Yahoo
1-minute QQQ/TQQQ bars via yfinance in AWS. The current and previous signals,
market snapshot, receipt and cumulative audit live only in versioned S3.
No GitHub, no broker, no retrospective fills and no implicit bootstrap.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
from datetime import date, datetime, time, timezone
import hashlib
import json
import math
import os
from zoneinfo import ZoneInfo

from stocklens.paper import (
    SessionMarket,
    _apply_corporate_actions,
    fetch_execution_market,
    mark_session,
    new_state,
    rebalance_if_required,
)
from paper_portfolio_integrity import evaluate

from infra.aws.independent_pipeline import canonical, _immutable_put
from infra.aws import session_continuity as sc

NY = ZoneInfo("America/New_York")
SHADOW_MODE = "SHADOW_ONLY_NO_BROKER_ACTIONS"
AUDIT_PASS = "PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS"
BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK"
GENESIS_KEY = f"paper/book/{BOOK}/genesis.json"
MAX_RECEIPT = 8_000_000


def previous_xnys_session(session: str) -> str:
    import exchange_calendars as xcals
    normalized = date.fromisoformat(session)
    if normalized.isoformat() != session:
        raise ValueError("NON_CANONICAL_SESSION_DATE")
    cal = xcals.get_calendar("XNYS")
    if not cal.is_session(session):
        raise ValueError("NOT_XNYS_SESSION")
    return cal.previous_session(session).date().isoformat()


def _timestamp(report: dict) -> datetime:
    ts = datetime.fromisoformat(report["generated_at_utc"].replace("Z", "+00:00"))
    if ts.tzinfo is None:
        raise ValueError("SIGNAL_TIMESTAMP_NAIVE")
    return ts.astimezone(timezone.utc)


def _checked_signal(report: dict, session: str, now: datetime):
    if report.get("mode") != SHADOW_MODE or not str(report.get("version", "")).startswith("8.0"):
        raise ValueError("FROZEN_SHADOW_SIGNAL_REQUIRED")
    if report.get("signal_source") != "QQQ_ADJUSTED_DAILY_CLOSE":
        raise ValueError("UNEXPECTED_SIGNAL_SOURCE")
    if report.get("execution_plan", {}).get("broker_actions_enabled") is not False:
        raise ValueError("BROKER_ACTIONS_PROHIBITED")
    if report.get("latest", {}).get("asof_date") != session:
        raise ValueError("SIGNAL_SESSION_MISMATCH")
    created = _timestamp(report)
    if created > now:
        raise ValueError("FUTURE_SIGNAL_GENERATION")
    target = report["latest"]
    if type(target.get("level")) is not int or target["level"] not in (1, 2, 3):
        raise ValueError("INVALID_FROZEN_LEVEL")
    if type(target.get("defense_active")) is not bool:
        raise ValueError("INVALID_FROZEN_DEFENSE")
    lev = target.get("target_leverage")
    expected = 0.0 if target["defense_active"] else {1: 1.25, 2: 2., 3: 3.}[target["level"]]
    if isinstance(lev, bool) or not isinstance(lev, (float, int)) or not math.isclose(lev, expected, abs_tol=1e-9):
        raise ValueError("INVALID_FROZEN_LEVERAGE")
    return created


def _checked_market(market: SessionMarket, expected: str):
    if market.session_date != expected or market.source != "YFINANCE_1M_RAW":
        raise ValueError("UNEXPECTED_OBSERVED_EXECUTION_SOURCE")
    for k in ("prices_0931", "prices_0932", "closes"):
        values = getattr(market, k)
        if set(values) != {"QQQ", "TQQQ"} or any(
            not math.isfinite(float(v)) or float(v) <= 0 for v in values.values()
        ):
            raise ValueError("INVALID_OBSERVED_MARKET:" + k)
    for k in ("dividends", "split_ratios"):
        values = getattr(market, k)
        if set(values) != {"QQQ", "TQQQ"} or any(
            not math.isfinite(float(v)) or float(v) < 0 for v in values.values()
        ):
            raise ValueError("INVALID_CORPORATE_ACTION:" + k)


def build_paper_receipt(
    *, session: str, current_signal: dict, prior_signal: dict,
    market: SessionMarket, now: datetime, previous_receipt: dict | None,
    previous_receipt_sha256: str | None = None, bootstrap: bool = False,
    max_age_days: int = 5,
):
    """Deterministic pure frozen-math receipt; no fetching or S3 in this function."""
    if now.tzinfo is None:
        raise ValueError("NAIVE_CLOCK")
    now = now.astimezone(timezone.utc)
    prior_day = previous_xnys_session(session)
    ny = now.astimezone(NY)
    if ny.date() < date.fromisoformat(session) or (
        ny.date() == date.fromisoformat(session) and ny.time() < time(18, 0)
    ):
        raise ValueError("PAPER_SESSION_NOT_COMPLETED")
    if max_age_days not in (5, 10):
        raise ValueError("UNSUPPORTED_PAPER_AGE_WINDOW")
    if (ny.date() - date.fromisoformat(session)).days > max_age_days:
        raise ValueError("PAPER_SESSION_TOO_OLD")
    current_at = _checked_signal(current_signal, session, now)
    prior_at = _checked_signal(prior_signal, prior_day, now)
    open_at = datetime.combine(date.fromisoformat(session), time(9, 30), NY)
    if prior_at >= open_at.astimezone(timezone.utc):
        raise ValueError("PRIOR_SIGNAL_CREATED_AFTER_MARKET_OPEN")
    if current_at < open_at.astimezone(timezone.utc):
        raise ValueError("CURRENT_SIGNAL_PREDATES_SESSION")
    _checked_market(market, session)

    if previous_receipt is None:
        if bootstrap is not True or previous_receipt_sha256 is not None:
            raise ValueError("EXPLICIT_PROSPECTIVE_BOOTSTRAP_REQUIRED")
        state = new_state()
        ledger = []
        trades_history = []
        snapshots = {}
        bootstrap_start = session
    else:
        if bootstrap:
            raise ValueError("REBOOTSTRAP_NOT_ALLOWED")
        if not previous_receipt_sha256 or len(previous_receipt_sha256) != 64:
            raise ValueError("PREVIOUS_RECEIPT_SHA_REQUIRED")
        if previous_receipt.get("session") != prior_day or previous_receipt.get("book") != BOOK:
            raise ValueError("PAPER_CHAIN_GAP_OR_BOOK_MISMATCH")
        if previous_receipt.get("integrity", {}).get("status") != AUDIT_PASS:
            raise ValueError("PREVIOUS_PAPER_INTEGRITY_FAILED")
        state = deepcopy(previous_receipt["state"])
        if state.get("last_mark_session") != prior_day:
            raise ValueError("PREVIOUS_STATE_SESSION_MISMATCH")
        ledger = deepcopy(previous_receipt["history"]["ledger"])
        trades_history = deepcopy(previous_receipt["history"]["trades"])
        snapshots = deepcopy(previous_receipt["history"]["signal_snapshots"])
        if len(ledger) != previous_receipt["integrity"]["verified_paper_sessions"]:
            raise ValueError("PREVIOUS_HISTORY_LENGTH_MISMATCH")
        if not ledger or ledger[-1]["session_date"] != prior_day:
            raise ValueError("PREVIOUS_LEDGER_LAST_DAY_MISMATCH")
        if not math.isclose(state["cash"], ledger[-1]["cash"], rel_tol=0, abs_tol=1e-6):
            raise ValueError("PREVIOUS_CASH_MISMATCH")
        if any(state["shares"][s] != ledger[-1][s.lower()+"_shares"] for s in ("QQQ", "TQQQ")):
            raise ValueError("PREVIOUS_HOLDINGS_MISMATCH")
        bootstrap_start = previous_receipt["bootstrap_start"]

    if prior_day in snapshots and canonical(snapshots[prior_day]) != canonical(prior_signal):
        raise ValueError("DIVERGENT_PRIOR_SIGNAL_SNAPSHOT")
    snapshots[prior_day] = prior_signal
    actions = _apply_corporate_actions(state, market)
    trades = rebalance_if_required(
        state, prior_signal, market, bootstrap=previous_receipt is None
    )
    row = mark_session(
        state, prior_signal, market, trades, actions,
        bootstrap=previous_receipt is None
    )
    ledger.append(row)
    trades_history.extend(trades)
    integrity = evaluate(ledger, trades_history, snapshots)
    if integrity["status"] != AUDIT_PASS:
        raise RuntimeError("INDEPENDENT_FULL_LEDGER_AUDIT_FAILED:" +
                           ",".join(integrity.get("errors", [])))
    if integrity["latest_session"] != session or integrity["equity"] is None:
        raise RuntimeError("AUDIT_LAST_SESSION_MISMATCH")

    # This model estimates fills using observed minute-bar opens and assumed
    # costs; broker_fills_observed remains false in every S3 receipt.
    receipt = {
        "schema_version": 1,
        "session": session,
        "book": BOOK,
        "bootstrap_start": bootstrap_start,
        "mode": SHADOW_MODE,
        "signal_date": prior_day,
        "prior_receipt_sha256": previous_receipt_sha256,
        "market_sha256": hashlib.sha256(canonical(asdict(market))).hexdigest(),
        "row": row,
        "trades": trades,
        "state": state,
        "history": {
            "ledger": ledger,
            "trades": trades_history,
            "signal_snapshots": snapshots,
        },
        "integrity": integrity,
        "broker_orders_authorized": False,
        "broker_fills_observed": False,
        "production_replacement_authorized": False,
    }
    if len(canonical(receipt)) > MAX_RECEIPT:
        raise RuntimeError("PAPER_RECEIPT_TOO_LARGE_NEEDS_CHECKPOINTING")
    return receipt


def _s3_read(s3, bucket: str, key: str) -> tuple[bytes, str]:
    raw, version_id, _ = _s3_read_meta(s3, bucket, key)
    return raw, version_id


def _is_missing(exc: Exception) -> bool:
    code = getattr(exc, "response", {}).get("Error", {}).get("Code")
    return code in ("NoSuchKey", "404", "NotFound") or type(exc).__name__ == "Missing"


def _s3_read_meta(s3, bucket: str, key: str):
    """Returns (body, version_id, server LastModified or None)."""
    obj = s3.get_object(Bucket=bucket, Key=key)
    last_modified = obj.get("LastModified")
    version_id = obj.get("VersionId")
    if not version_id or version_id == "null":
        raise RuntimeError("S3_VERSION_ID_REQUIRED:" + key)
    raw = obj["Body"].read(MAX_RECEIPT + 1)
    if len(raw) > MAX_RECEIPT:
        raise RuntimeError("S3_RECEIPT_TOO_LARGE:" + key)
    if last_modified is not None and last_modified.tzinfo is None:
        raise RuntimeError("S3_LAST_MODIFIED_NAIVE:" + key)
    return raw, version_id, last_modified


def _continuity_key(session: str) -> str:
    return f"paper/continuity/{session}.json"


def _read_continuity(s3, bucket: str, session: str):
    try:
        raw, version, _ = _s3_read_meta(s3, bucket, _continuity_key(session))
    except Exception as exc:
        if _is_missing(exc):
            return None, None
        raise
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


MAX_CHAIN_SESSIONS = 400


def s3_object_sha256_and_time(s3, bucket: str, key: str):
    """(hex sha256, LastModified) from S3 metadata, or (None, None) if absent.
    Uses the server-computed ChecksumSHA256 via HeadObject when available; falls back to
    downloading and hashing (objects written before checksums, or test fakes)."""
    import base64
    try:
        head = s3.head_object(Bucket=bucket, Key=key, ChecksumMode="ENABLED")
    except Exception as exc:
        if _is_missing(exc):
            return None, None
        if not isinstance(exc, AttributeError):
            raise
        head = None
    if head is not None and head.get("ChecksumSHA256") and "-" not in head["ChecksumSHA256"]:
        return base64.b64decode(head["ChecksumSHA256"]).hex(), head.get("LastModified")
    try:
        raw, _, last_modified = _s3_read_meta(s3, bucket, key)
    except Exception as exc:
        if _is_missing(exc):
            return None, None
        raise
    return hashlib.sha256(raw).hexdigest(), last_modified


def verify_book_chain(s3, bucket: str, *, through_session: str, genesis: dict) -> int:
    """Fully re-verify the continuity chain from the durable genesis through
    ``through_session``: genesis binding, every record (recomputed counters, timing,
    adjacency), receipt SHA and genuine S3 server times. Raises on any defect."""
    import exchange_calendars as xcals
    start = genesis.get("bootstrap_session")
    cal = xcals.get_calendar("XNYS")
    if not isinstance(start, str) or not cal.is_session(start) or start > through_session:
        raise RuntimeError("PREVIOUS_CHAIN_UNVERIFIED:GENESIS_SESSION")
    sessions = [d.date().isoformat() for d in cal.sessions_in_range(start, through_session)]
    if len(sessions) > MAX_CHAIN_SESSIONS:
        raise RuntimeError("PREVIOUS_CHAIN_UNVERIFIED:APPROVED_CHECKPOINT_REQUIRED")
    prev = None
    for day in sessions:
        rec, _ = _read_continuity(s3, bucket, day)
        if rec is None:
            raise RuntimeError("PREVIOUS_CHAIN_UNVERIFIED:MISSING_RECORD:" + day)
        if prev is None:
            g = sc.validate_genesis(genesis, rec, book=BOOK)
            if g:
                raise RuntimeError("PREVIOUS_CHAIN_UNVERIFIED:" + day + ":" + ",".join(g))
        receipt_sha, receipt_at = s3_object_sha256_and_time(s3, bucket, f"paper/sessions/{day}.json")
        _, signal_at = s3_object_sha256_and_time(
            s3, bucket, f"signals/{previous_xnys_session(day)}.json")
        errs = sc.validate_record(rec, session=day, book=BOOK, previous=prev,
                                  receipt_sha256=receipt_sha, receipt_saved_at=receipt_at,
                                  signal_saved_at=signal_at, check_s3_times=True)
        if errs:
            raise RuntimeError("PREVIOUS_CHAIN_UNVERIFIED:" + day + ":" + ",".join(errs))
        prev = rec
    return len(sessions)


def _read_genesis(s3, bucket: str):
    try:
        raw, _, _ = _s3_read_meta(s3, bucket, GENESIS_KEY)
    except Exception as exc:
        if _is_missing(exc):
            return None
        raise
    return json.loads(raw)


def _write_continuity(s3, bucket: str, *, session: str, status: str, now: datetime,
                      signal_archived_at, reason=None, evidence=None, bootstrap=False):
    existing, _ = _read_continuity(s3, bucket, session)
    if existing is not None:
        # Idempotent retry only if the recomputed classification is identical;
        # anything else is contradictory evidence and fails closed.
        same = (existing.get("status") == status
                and (existing.get("evidence") or {}).get("paper_sha256")
                == (evidence or {}).get("paper_sha256"))
        if not same:
            raise RuntimeError("CONTINUITY_CONFLICT:" + session)
        return existing
    if bootstrap:
        prev, prev_sha = None, None
    else:
        prev, prev_sha = _read_continuity(s3, bucket, previous_xnys_session(session))
        if prev is None:
            raise RuntimeError("MISSING_PREVIOUS_CONTINUITY_RECORD_FAIL_CLOSED")
    record = sc.build_record(
        session=session, status=status, previous_record=prev,
        previous_record_sha256=prev_sha, processed_at=now,
        signal_archived_at=signal_archived_at, reason=reason,
        evidence=evidence, book=BOOK)
    _immutable_put(s3, bucket, _continuity_key(session), canonical(record), "application/json")
    return record


def run_paper(*, session: str, now: datetime, s3, bucket: str,
              bootstrap: bool = False, market_fetch=fetch_execution_market,
              max_age_days: int = 5) -> dict:
    prior_day = previous_xnys_session(session)
    # ---- Guards evaluated BEFORE any write ----
    own, _ = _read_continuity(s3, bucket, session)
    if own is not None and own.get("status") == sc.MISSED:
        raise RuntimeError("SESSION_CLASSIFIED_MISSED_CONFLICT_BOOK_HALTED:" + session)
    prev_cont, _ = _read_continuity(s3, bucket, prior_day)
    if prev_cont is not None and prev_cont.get("book_halted"):
        raise RuntimeError("BOOK_HALTED_AFTER_MISSED_SESSION_HUMAN_RESUME_REQUIRED:" + prior_day)
    genesis = _read_genesis(s3, bucket)
    if not bootstrap:
        if prev_cont is None:
            raise RuntimeError("MISSING_PREVIOUS_CONTINUITY_RECORD_FAIL_CLOSED:" + prior_day)
        if genesis is None:
            raise RuntimeError("BOOK_GENESIS_MISSING_CHAIN_UNANCHORED")
        # Full verification from genesis BEFORE any write (not a shallow field check).
        verify_book_chain(s3, bucket, through_session=prior_day, genesis=genesis)
    if bootstrap:
        if genesis is not None and genesis.get("bootstrap_session") != session:
            raise RuntimeError("REBOOTSTRAP_NOT_ALLOWED_BOOK_EXISTS:" + str(genesis.get("bootstrap_session")))
        if prev_cont is not None:
            raise RuntimeError("REBOOTSTRAP_NOT_ALLOWED_BOOK_HAS_CONTINUITY")
    # Source contracts are read from immutable S3 objects (never GitHub).
    curr_raw, curr_version, _ = _s3_read_meta(s3, bucket, f"signals/{session}.json")
    prior_raw, prior_version, prior_archived_at = _s3_read_meta(
        s3, bucket, f"signals/{prior_day}.json")
    current_signal, prior_signal = json.loads(curr_raw), json.loads(prior_raw)
    key_previous = f"paper/sessions/{prior_day}.json"
    try:
        previous_raw, previous_version = _s3_read(s3, bucket, key_previous)
    except Exception as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if code not in ("NoSuchKey", "404", "NotFound"):
            raise
        previous_raw = None
        previous_version = None
    if bootstrap and previous_raw is not None:
        raise RuntimeError("PAPER_PREVIOUS_SESSION_EXISTS_CANNOT_BOOTSTRAP")
    if not bootstrap and previous_raw is None:
        raise RuntimeError("MISSING_PAPER_PREVIOUS_SESSION_FAIL_CLOSED")
    previous = json.loads(previous_raw) if previous_raw is not None else None

    market = market_fetch(prior_day, session)
    receipt = build_paper_receipt(
        session=session, current_signal=current_signal, prior_signal=prior_signal,
        market=market, now=now, previous_receipt=previous,
        previous_receipt_sha256=hashlib.sha256(previous_raw).hexdigest() if previous_raw else None,
        bootstrap=bootstrap, max_age_days=max_age_days,
    )
    normalized_market = {
        "source": "YFINANCE_1M_RAW",
        "observed_values": asdict(market),
        "modelled_execution_not_broker_fills": True,
        "vendor_raw_http_response_archived": False,
        "current_signal_version_id": curr_version,
        "prior_signal_version_id": prior_version,
        "previous_receipt_version_id": previous_version,
    }
    market_body = canonical(normalized_market)
    market_sha = hashlib.sha256(canonical(asdict(market))).hexdigest()
    if market_sha != receipt["market_sha256"]:
        raise RuntimeError("MARKET_RECEIPT_FINGERPRINT_MISMATCH")
    market_key = f"market/paper/{session}.json"
    market_version = _immutable_put(s3, bucket, market_key, market_body, "application/json")
    receipt["market_key"] = market_key
    receipt["market_version_id"] = market_version
    receipt["current_signal_sha256"] = hashlib.sha256(curr_raw).hexdigest()
    receipt["prior_signal_sha256"] = hashlib.sha256(prior_raw).hexdigest()
    final = canonical(receipt)
    key = f"paper/sessions/{session}.json"
    version = _immutable_put(s3, bucket, key, final, "application/json")
    # Completion time = S3 server time the receipt was durably saved (on an idempotent
    # retry this is the ORIGINAL save), never the Lambda's start clock.
    stored, _, saved_at = _s3_read_meta(s3, bucket, key)
    if saved_at is None:
        raise RuntimeError("S3_SERVER_LAST_MODIFIED_REQUIRED:" + key)
    if hashlib.sha256(stored).digest() != hashlib.sha256(final).digest():
        raise RuntimeError("STORED_RECEIPT_MISMATCH:" + key)
    status = sc.classify(session=session, signal_archived_at=prior_archived_at,
                         processed_at=saved_at, accounting_completed=True)
    continuity = _write_continuity(
        s3, bucket, session=session, status=status, now=saved_at,
        signal_archived_at=prior_archived_at, bootstrap=bootstrap,
        evidence={"paper_key": key, "paper_version_id": version,
                  "paper_sha256": hashlib.sha256(final).hexdigest()})
    if bootstrap:
        # Two-phase bootstrap: genesis is the COMMIT, written only after the receipt and
        # its continuity record exist, and it binds to both by hash. A failed bootstrap
        # leaves no genesis; a crash before this line is completed by an identical rerun.
        # Concurrent bootstraps of different sessions race on IfNoneMatch: exactly one
        # genesis wins; the loser fails (DIVERGENT_IMMUTABLE_S3_OBJECT) and its objects
        # remain unanchored and are never accepted by verify_book_chain / the watchdog.
        _immutable_put(s3, bucket, GENESIS_KEY,
                       canonical(sc.build_genesis(book=BOOK, first_record=continuity)),
                       "application/json")
    return {
        "status": "STAGED_PAPER_VERIFIED",
        "continuity_status": continuity["status"],
        "continuity_epoch": continuity["epoch"],
        "session": session,
        "book": BOOK,
        "paper_key": key,
        "paper_version_id": version,
        "paper_sha256": hashlib.sha256(final).hexdigest(),
        "equity": receipt["row"]["equity"],
        "trade_count": len(receipt["trades"]),
        "audit": receipt["integrity"]["status"],
        "broker_fills": False,
        "broker_orders": False,
    }


class ExecutionDataUnavailable(RuntimeError):
    pass


class ProviderUnavailable(RuntimeError):
    """Raise from a market adapter ONLY when observations are genuinely absent."""


# Exact PaperIntegrityError codes from stocklens.paper meaning "observations absent".
# Everything else from the same exception class (DUPLICATE_MINUTE_BARS,
# INVALID_EXEC_PRICE, NON_XNYS_PAPER_SESSION, ACTION_FETCH_FAILED, ...) is an
# integrity/parsing failure and must propagate unchanged.
_ABSENCE_CODE = __import__("re").compile(
    r"^(MISSING_\d{4}_BAR:|MISSING_NEAR_SESSION_CLOSE:|NO_COMMON_EXECUTION_SESSION$)")


def is_provider_unavailable(exc: BaseException) -> bool:
    """True ONLY for definitive absence of observations (-> MISSED_UNRECOVERABLE).

    Transient failures (timeouts, connection errors, HTTP errors) are deliberately NOT
    included: they propagate, the orchestrator invocation fails (OnFailure + Errors
    alarm), and the next night's bounded catch-up retries the session. A session is only
    declared unrecoverable when the provider definitively lacks the bars. Nothing
    recovered later is ever counted as contemporaneous execution evidence.
    """
    from stocklens.paper import PaperIntegrityError
    if isinstance(exc, ProviderUnavailable):
        return True
    if type(exc) is PaperIntegrityError and _ABSENCE_CODE.match(str(exc)):
        return True
    return False


def run_paper_catchup(*, target_session: str, now: datetime, s3, bucket: str,
                      market_fetch=fetch_execution_market) -> dict:
    """Process every unrecorded session up to target, oldest first, bounded horizon.

    Missing *inputs* (signal never archived, observed bars unavailable) produce one
    MISSED_UNRECOVERABLE record and halt. Any other error (integrity, math, chain) is
    raised unchanged -- bugs are never reclassified as missed sessions.
    """
    probe, last = target_session, None
    for _ in range(sc.MAX_CATCHUP_SESSIONS + 1):
        rec, _ = _read_continuity(s3, bucket, probe)
        if rec is not None:
            last = rec
            break
        probe = previous_xnys_session(probe)
    if last is None:
        raise RuntimeError("NO_CONTINUITY_HEAD_WITHIN_HORIZON_HUMAN_REVIEW_REQUIRED")
    if last["book_halted"]:
        raise RuntimeError("BOOK_HALTED_AFTER_MISSED_SESSION_HUMAN_RESUME_REQUIRED:" + last["session"])
    pending = sc.plan_catchup(last_recorded_session=last["session"], target_session=target_session)
    if not pending:
        # Nothing new: prove the already-stored receipt instead of returning null.
        if last["session"] != target_session:
            raise RuntimeError("CONTINUITY_HEAD_AHEAD_OF_TARGET")
        raw, _, _ = _s3_read_meta(s3, bucket, f"paper/sessions/{target_session}.json")
        sha = hashlib.sha256(raw).hexdigest()
        if (last.get("evidence") or {}).get("paper_sha256") != sha:
            raise RuntimeError("STORED_RECEIPT_DOES_NOT_MATCH_CONTINUITY:" + target_session)
        return {"status": "STAGED_PAPER_CATCHUP_COMPLETED", "session": target_session,
                "sessions": [], "paper_sha256": sha, "idempotent_noop": True,
                "broker_actions": False, "broker_fills": False, "broker_orders": False}
    done = []
    for session in pending:
        def guarded_fetch(prior, sess):
            try:
                return market_fetch(prior, sess)
            except Exception as exc:
                if not is_provider_unavailable(exc):
                    raise          # schema / parser / logic errors propagate unchanged
                raise ExecutionDataUnavailable(f"{type(exc).__name__}:{str(exc)[:120]}") from exc
        try:
            result = run_paper(session=session, now=now, s3=s3, bucket=bucket,
                               market_fetch=guarded_fetch, max_age_days=10)
        except ExecutionDataUnavailable as exc:
            rec = _write_continuity(s3, bucket, session=session, status=sc.MISSED, now=now,
                                    signal_archived_at=None,
                                    reason="OBSERVED_EXECUTION_BARS_UNAVAILABLE:" + str(exc))
            done.append({"session": session, "continuity_status": rec["status"]})
            break
        except Exception as exc:
            if not _is_missing(exc):
                raise
            rec = _write_continuity(s3, bucket, session=session, status=sc.MISSED, now=now,
                                    signal_archived_at=None,
                                    reason="REQUIRED_ARCHIVED_SIGNAL_MISSING")
            done.append({"session": session, "continuity_status": rec["status"]})
            break
        done.append({"session": session, "continuity_status": result["continuity_status"],
                     "paper_sha256": result["paper_sha256"]})
    halted = bool(done) and done[-1]["continuity_status"] == sc.MISSED
    return {
        "status": "STAGED_PAPER_HALTED" if halted else "STAGED_PAPER_CATCHUP_COMPLETED",
        "session": target_session,
        "sessions": done,
        "paper_sha256": done[-1].get("paper_sha256") if done and not halted else None,
        "broker_actions": False,
        "broker_fills": False,
        "broker_orders": False,
    }



def preflight_prospective_paper_bootstrap(
    *, session: str, now: datetime, s3, bucket: str,
    market_fetch=fetch_execution_market,
) -> dict:
    """READ-ONLY test of the *first* prospective staging Paper session.

    It never calls _immutable_put or any broker. It refuses retrospectively
    fabricated sessions, existing paper books, or unaudited prior-close timing.
    Paper still requires a separate explicit operator-approved bootstrap.
    """
    if now.tzinfo is None:
        raise RuntimeError("PREFLIGHT_CLOCK_MUST_BE_AWARE")
    now = now.astimezone(timezone.utc)
    # The prospective execution session must be fully closed, yet its NEXT
    # market open must not have arrived. This lets the owner run the review
    # next morning in Israel, without promoting late/backfilled evidence.
    if not (sc.session_close_utc(session) <= now <
            sc.accounting_deadline_utc(session)):
        raise RuntimeError("PREFLIGHT_REQUIRES_COMPLETED_SESSION_BEFORE_NEXT_OPEN")
    prior = previous_xnys_session(session)
    if _read_genesis(s3, bucket) is not None:
        raise RuntimeError("PREFLIGHT_REFUSE_EXISTING_PAPER_BOOK")
    own_cont, _ = _read_continuity(s3, bucket, session)
    prev_cont, _ = _read_continuity(s3, bucket, prior)
    if own_cont is not None or prev_cont is not None:
        raise RuntimeError("PREFLIGHT_REFUSE_EXISTING_PAPER_CONTINUITY")
    # Read-only preflight must reject partially written first-session objects
    # too: a crashed bootstrap could have written the observed market or
    # modelled receipt without committing continuity or Genesis. Those
    # immutable objects cannot safely be mistaken for a fresh empty book.
    for key in (
        f"paper/sessions/{prior}.json",
        f"paper/sessions/{session}.json",
        f"market/paper/{prior}.json",
        f"market/paper/{session}.json",
    ):
        try:
            _s3_read_meta(s3, bucket, key)
        except Exception as exc:
            if not _is_missing(exc):
                raise
        else:
            raise RuntimeError("PREFLIGHT_REFUSE_EXISTING_PARTIAL_PAPER_OBJECT:" + key)

    curr_raw, curr_version, curr_saved = _s3_read_meta(
        s3, bucket, f"signals/{session}.json")
    prior_raw, prior_version, prior_saved = _s3_read_meta(
        s3, bucket, f"signals/{prior}.json")
    if curr_saved is None or prior_saved is None:
        raise RuntimeError("PREFLIGHT_S3_SERVER_TIMES_REQUIRED")
    if curr_saved.tzinfo is None or prior_saved.tzinfo is None:
        raise RuntimeError("PREFLIGHT_NAIVE_S3_SERVER_TIME")
    if not (sc.session_close_utc(prior) <= prior_saved < sc.session_open_utc(session)):
        raise RuntimeError("PREFLIGHT_PRIOR_SIGNAL_NOT_ARCHIVED_BEFORE_OPEN")
    if not (sc.session_close_utc(session) <= curr_saved <= now.astimezone(timezone.utc)):
        raise RuntimeError("PREFLIGHT_CURRENT_SIGNAL_NOT_ARCHIVED_AFTER_CLOSE")
    current = json.loads(curr_raw)
    previous = json.loads(prior_raw)
    # Validates frozen 8.0 mode, session identity, leverage and self timestamps.
    _checked_signal(previous, prior, now)
    _checked_signal(current, session, now)
    observed = market_fetch(prior, session)
    modeled = build_paper_receipt(
        session=session, current_signal=current, prior_signal=previous,
        market=observed, now=now, previous_receipt=None,
        bootstrap=True, max_age_days=5,
    )
    return {
        "status": "STAGING_PAPER_BOOTSTRAP_PREFLIGHT_PASS_READ_ONLY",
        "session": session,
        "prior_session": prior,
        "prior_signal_s3_version_id": prior_version,
        "current_signal_s3_version_id": curr_version,
        "prior_signal_s3_sha256": hashlib.sha256(prior_raw).hexdigest(),
        "current_signal_s3_sha256": hashlib.sha256(curr_raw).hexdigest(),
        "prior_signal_s3_saved_at_utc": prior_saved.isoformat(),
        "current_signal_s3_saved_at_utc": curr_saved.isoformat(),
        "market_source": observed.source,
        "model_candidate_sha256": hashlib.sha256(canonical(modeled)).hexdigest(),
        "paper_model_equity": modeled["row"]["equity"],
        "paper_model_trades": len(modeled["trades"]),
        "paper_accounting_audit": modeled["integrity"]["status"],
        "broker_actions": False,
        "broker_orders": False,
        "broker_fills": False,
        "market_data_written": False,
        "paper_data_written": False,
        "genesis_written": False,
        "prospective_bootstrap_authorized": False,
    }

def _import_smoke():
    # Imports target native Linux wheels without an intraday provider request.
    import importlib
    for package in ("numpy", "pandas", "yfinance", "exchange_calendars",
                    "stocklens.paper", "paper_portfolio_integrity", "boto3"):
        importlib.import_module(package)
    if not os.environ.get("STOCKLENS_DATA_BUCKET"):
        raise RuntimeError("STAGING_BUCKET_ENV_MISSING")
    return {"status": "STAGING_IMPORT_OK", "component": "paper",
            "broker_actions": False, "market_data_written": False}


def preflight_handler(event, context):
    """Least-privilege staging Lambda entrypoint: NEVER exposes Paper writes.

    CloudFormation binds this handler to a distinct read-only IAM role. The
    existing writable Paper Lambda and its handler remain unchanged.
    """
    if (event or {}).get("mode") == "STAGING_IMPORT_SMOKE":
        smoke = _import_smoke()
        smoke["component"] = "paper_preflight"
        return smoke
    if (event or {}).get("mode") != "STAGING_PAPER_BOOTSTRAP_PREFLIGHT":
        raise RuntimeError("PREFLIGHT_ONLY_LAMBDA_MODE_REQUIRED")
    if event.get("bootstrap") not in (None, False):
        raise RuntimeError("PREFLIGHT_NEVER_BOOTSTRAPS")
    import boto3
    return preflight_prospective_paper_bootstrap(
        session=event["expected_session"], now=datetime.now(timezone.utc),
        s3=boto3.client("s3"), bucket=os.environ["STOCKLENS_DATA_BUCKET"],
    )


def handler(event, context):
    if event.get("mode") == "STAGING_IMPORT_SMOKE":
        return _import_smoke()
    import boto3
    if event.get("mode") == "STAGING_PAPER_CATCHUP":
        if event.get("bootstrap") not in (None, False):
            raise RuntimeError("CATCHUP_CANNOT_BOOTSTRAP")
        return run_paper_catchup(
            target_session=event["expected_session"], now=datetime.now(timezone.utc),
            s3=boto3.client("s3"), bucket=os.environ["STOCKLENS_DATA_BUCKET"])
    if event.get("mode") != "STAGING_PAPER_ONLY":
        raise RuntimeError("STAGING_PAPER_MODE_REQUIRED")
    return run_paper(
        session=event["expected_session"],
        now=datetime.now(timezone.utc),
        s3=boto3.client("s3"),
        bucket=os.environ["STOCKLENS_DATA_BUCKET"],
        bootstrap=event.get("bootstrap") is True,
    )

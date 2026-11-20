"""Fail-closed immutable S3 Paper+Continuity writes for a *future* Epoch5 runtime.

NO AWS client created, NO executable main, NO scheduler, NO broker access.
Provides an opt-in reusable storage primitive for a NEW epoch; it does not
modify or recover the existing deployed independent_paper.handler by itself.

S3 is not transactional across multiple keys: a failed Continuity write may
leave Paper alone. The next attempt must regenerate the EXACT SAME canonical
Paper bytes and reuse the VERIFIED existing VersionId before writing the
missing Continuity. It must never recalculate trading orders in between,
overwrite history, invent a missing day, or silently treat 412 as success.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import re

EPOCH = "NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH5_20261120"
PREFIX = "paper/epochs/" + EPOCH + "/"
MIN_SESSION = date(2026, 11, 20)
ST_BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
MAX_BYTES = 2_000_000
SCHEMA = "stocklens-epoch5-immutable-paper-v1"
SHA_RE = re.compile(r"[0-9a-f]{64}\Z")
VERSION_RE = re.compile(r"[^\s]{1,256}\Z")
DAY_RE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


class ImmutableEpoch5Error(RuntimeError):
    """No recovery is allowed until the exact source state is verified."""


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise ImmutableEpoch5Error(reason)


def canonical(payload: dict) -> bytes:
    require(type(payload) is dict, "PAYLOAD_MUST_BE_OBJECT")
    return (json.dumps(payload, sort_keys=True, separators=(",",":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def validate_session(session: str) -> str:
    require(isinstance(session,str) and DAY_RE.fullmatch(session) is not None,
            "BAD_SESSION_DATE")
    try:
        day=date.fromisoformat(session)
    except ValueError as e:
        raise ImmutableEpoch5Error("INVALID_SESSION_DATE") from e
    require(day>=MIN_SESSION, "NO_HISTORICAL_EPOCH5_BACKFILL")
    return session


def key_for(kind: str, session: str | None = None) -> str:
    if kind=="genesis":
        require(session is None, "GENESIS_HAS_NO_SESSION_KEY")
        return PREFIX+"genesis.json"
    require(kind in ("sessions","continuity"), "WRITER_KEY_ROLE_NOT_APPROVED")
    day=validate_session(session)
    return PREFIX+kind+"/"+day+".json"


def _approved_key(key: str) -> None:
    require(type(key) is str and key.startswith(PREFIX), "OUTSIDE_NEW_EPOCH_BLOCKED")
    tail=key[len(PREFIX):]
    if tail=="genesis.json":
        return
    for kind in ("sessions","continuity"):
        if tail.startswith(kind+"/") and tail.endswith(".json"):
            session=tail[len(kind)+1:-5]
            if key_for(kind,session)==key:
                return
    raise ImmutableEpoch5Error("ONLY_IMMUTABLE_GENESIS_PAPER_CONTINUITY_KEYS")


@dataclass(frozen=True)
class VerifiedReceipt:
    key: str
    version_id: str
    sha256: str
    byte_count: int
    created: bool
    proven_exact_stored_bytes: bool = True


def _validated_version(value: object) -> str:
    require(isinstance(value,str) and bool(VERSION_RE.fullmatch(value)) and
            value.lower()!="null", "S3_VERSION_ID_REQUIRED")
    return value


def _verify_exact(s3, key: str, expected: bytes,
                  *, required_version: str | None = None) -> VerifiedReceipt:
    # A HEAD alone cannot prove immutable bytes; pin a version and GET that
    # exact version. Reject deletion, null version, wrong bytes or any drift.
    head=s3.head_object(Bucket=ST_BUCKET,Key=key)
    version=_validated_version(head.get("VersionId"))
    if required_version is not None:
        require(version==required_version, "LATEST_S3_VERSION_CHANGED_DURING_PUT")
    require(type(head.get("ContentLength")) is int and
            head["ContentLength"]==len(expected),
            "S3_BODY_LENGTH_MISMATCH")
    expected_sha=digest(expected)
    require((head.get("Metadata") or {}).get("sha256")==expected_sha,
            "S3_RECEIPT_METADATA_DIGEST_MISMATCH")
    obj=s3.get_object(Bucket=ST_BUCKET,Key=key,VersionId=version)
    require(obj.get("VersionId")==version, "S3_PINNED_GET_VERSION_DRIFT")
    raw=obj["Body"].read(MAX_BYTES+1)
    require(raw==expected and len(raw)==len(expected),
            "S3_EXISTING_IMMUTABLE_BYTES_DIFFER")
    require(digest(raw)==expected_sha,"S3_VERIFIED_SHA_MISMATCH")
    return VerifiedReceipt(key,version,expected_sha,len(raw),created=False)


def _error_code(exc: Exception) -> str:
    return str((getattr(exc,"response",{}) or {}).get("Error",{}).get("Code",""))


def put_once_or_identical(s3, *, key: str, payload: dict) -> VerifiedReceipt:
    """Conditional PUT only; on 412 accept EXACT bytes after pinned readback.

    Unexpected S3 errors and 409 races fail closed, even when a client timeout
    *might* have followed a successful commit. The caller can retry later.
    """
    _approved_key(key)
    raw=canonical(payload)
    require(2<=len(raw)<=MAX_BYTES, "INVALID_IMMUTABLE_BODY_SIZE")
    sha=digest(raw)
    try:
        result=s3.put_object(
            Bucket=ST_BUCKET,Key=key,Body=raw,IfNoneMatch="*",
            ContentType="application/json",
            Metadata={"sha256":sha,"schema":SCHEMA})
    except Exception as exc:
        if _error_code(exc) not in ("PreconditionFailed","412"):
            raise ImmutableEpoch5Error(
                "S3_IMMUTABLE_PUT_FAILED_UNCERTAIN_NO_REPLAY") from exc
        # Do not re-PUT or claim success from 412. Verify the existing
        # VERSIONED object with exact same bytes and SHA first.
        return _verify_exact(s3,key,raw)
    version=_validated_version(result.get("VersionId"))
    verified=_verify_exact(s3,key,raw,required_version=version)
    return VerifiedReceipt(
        verified.key,verified.version_id,verified.sha256,
        verified.byte_count,created=True)


def _paper_shape(paper: dict, session: str) -> None:
    require(type(paper) is dict and paper.get("book")==EPOCH and
            paper.get("session")==session,
            "PAPER_WRONG_BOOK_OR_SESSION")
    require(paper.get("mode")=="SHADOW_ONLY_NO_BROKER_ACTIONS" and
            paper.get("broker_orders_authorized") is False and
            paper.get("broker_fills_observed") is False,
            "PAPER_REAL_BROKER_OR_UNATTESTED_MODE_BLOCKED")
    state=paper.get("state")
    require(type(state) is dict and state.get("last_mark_session")==session,
            "PAPER_INCOMPLETE_MARKED_STATE")


def _continuity_shape(obj: dict, session: str, paper: VerifiedReceipt) -> None:
    require(type(obj) is dict and obj.get("book")==EPOCH and
            obj.get("session")==session, "CONTINUITY_WRONG_BOOK_OR_SESSION")
    require(obj.get("broker_orders") is False and
            obj.get("broker_fills") is False,
            "CONTINUITY_MUST_BE_MODELED_ONLY")
    require(obj.get("status")=="MODELLED_RECEIPT_NOT_INDEPENDENTLY_QUALIFIED",
            "UNSUPPORTED_CONTINUITY_QUALIFIED_STATUS")
    evidence=obj.get("evidence")
    require(type(evidence) is dict and
            evidence.get("paper_sha256")==paper.sha256 and
            evidence.get("paper_version_id")==paper.version_id and
            evidence.get("paper_key")==paper.key,
            "CONTINUITY_MUST_PIN_EXACT_PAPER_BYTES_AND_VERSION")


def save_paper_and_continuity(s3, *, session: str, paper_payload: dict,
                              continuation_builder) -> dict:
    """Fail-closed crash-restartable pair; caller supplies stable prior proofs.

    This never computes economic trades and never manufactures historical
    signals/receipts. The builder may only construct a deterministic,
    NOT-YET-QUALIFIED Continuity receipt that references the exact persisted
    Paper version. Independent Watchdog verification is a separate step.
    """
    session=validate_session(session)
    _paper_shape(paper_payload,session)
    paper=put_once_or_identical(
        s3,key=key_for("sessions",session),payload=paper_payload)
    continuation=continuation_builder(paper)
    _continuity_shape(continuation,session,paper)
    evidence=put_once_or_identical(
        s3,key=key_for("continuity",session),payload=continuation)
    return {
        "status":"IMMUTABLE_EPOCH5_PAIR_STORED_VERIFIED_NOT_WATCHDOG_ATTESTED",
        "book":EPOCH,"session":session,
        "paper_sha256":paper.sha256,"paper_version_id":paper.version_id,
        "paper_created_now":paper.created,
        "continuity_sha256":evidence.sha256,
        "continuity_version_id":evidence.version_id,
        "continuity_created_now":evidence.created,
        "exact_s3_versions_read_back":True,
        "broker_orders":False,
        "epoch5_runtime_deployed":False,
    }

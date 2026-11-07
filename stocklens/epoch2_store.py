"""ST Epoch2 immutable S3 storage protocol — NOT WIRED TO A LAMBDA.

Can only write to a distinct epoch2 prefix. No broker, no old-book changes,
no alarm reset, no deployment. Any future private adapter must provide a
trusted verify_before_each_write callback that independently authenticates
AWS account, PROD disarmament, ST Lambda SHA, data and operator consent.
The callback is mandatory, not proof that integration is ready.

Conditional S3 writes, version-pinned readback, SHA links, byte-identical
retry, and fail-closed incomplete Paper->Continuity writes are implemented.
None of this alone is evidence of genuine simulated market fills or NAV.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Callable

from stocklens import paper_epoch as epoch

ST_BUCKET = "stocklens-st-candidatedata-6jj7i9fxjmfr"
PREFIX = epoch.NEW_PREFIX
GENESIS = PREFIX + "genesis.json"
GAPS = PREFIX + "incidents/missing-2026-11-05_2026-11-06.json"
MAX_BYTES = 1_000_000
DAY = re.compile(r"20[0-9]{2}-[0-9]{2}-[0-9]{2}\Z")


class EpochStorageBlocked(RuntimeError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise EpochStorageBlocked(message)


def encode(record: dict) -> bytes:
    require(isinstance(record, dict), "RECEIPT_NOT_OBJECT")
    raw = json.dumps(record, sort_keys=True, separators=(",", ":"),
                     allow_nan=False, ensure_ascii=True).encode("utf-8")
    require(2 <= len(raw) <= MAX_BYTES, "RECEIPT_BAD_SIZE")
    return raw


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def error_code(exc: Exception) -> str:
    return str((getattr(exc, "response", {}) or {}).get("Error", {}).get("Code", ""))


@dataclass(frozen=True)
class Receipt:
    key: str
    version: str
    sha256: str
    raw: bytes
    record: dict


class Epoch2Store:
    def __init__(self, s3: Any, *,
                 bucket: str = ST_BUCKET,
                 verify_before_each_write: Callable[[], None] | None = None):
        require(bucket == ST_BUCKET, "NOT_PINNED_ST_BUCKET")
        self.s3 = s3
        self.bucket = bucket
        self._guard = verify_before_each_write

    @staticmethod
    def _key(key: str) -> None:
        require(isinstance(key, str) and key.startswith(PREFIX) and
                key.endswith(".json") and ".." not in key and
                "//" not in key and len(key) < 240,
                "OUTSIDE_EPOCH2_NAMESPACE")

    def _versioning(self) -> None:
        require(self.s3.get_bucket_versioning(Bucket=self.bucket).get("Status")
                == "Enabled", "VERSIONING_REQUIRED")

    def read(self, key: str) -> Receipt | None:
        self._key(key)
        self._versioning()
        try:
            meta = self.s3.head_object(Bucket=self.bucket, Key=key)
        except Exception as exc:
            if error_code(exc) in ("404", "NotFound", "NoSuchKey"):
                return None
            raise EpochStorageBlocked("HEAD_FAIL_CLOSED:" + error_code(exc)) from exc
        ver, size = meta.get("VersionId"), meta.get("ContentLength")
        require(isinstance(ver, str) and ver not in ("", "null") and
                type(size) is int and 2 <= size <= MAX_BYTES,
                "INVALID_VERSIONED_HEAD")
        try:
            got = self.s3.get_object(
                Bucket=self.bucket, Key=key, VersionId=ver)
            require(got.get("VersionId") == ver, "S3_VERSION_MISMATCH")
            raw = got["Body"].read(MAX_BYTES + 1)
            require(len(raw) == size, "BODY_SIZE_MISMATCH")
            record = json.loads(raw)
        except EpochStorageBlocked:
            raise
        except Exception as exc:
            raise EpochStorageBlocked("PINNED_READ_FAIL_CLOSED") from exc
        require(isinstance(record, dict), "NON_OBJECT_RECEIPT")
        return Receipt(key, ver, digest(raw), raw, record)

    def _create(self, key: str, payload: dict) -> dict:
        self._key(key)
        require(callable(self._guard), "PRIVATE_WRITE_GUARD_NOT_CONNECTED")
        # A future audited private adapter must perform authentic AWS checks.
        require(self._guard() is None, "PRIVATE_GUARD_UNEXPECTED_RETURN")
        raw = encode(payload)
        current = self.read(key)
        if current is not None:
            require(current.raw == raw, "IMMUTABLE_CONFLICT")
            return {"key":key, "sha256":digest(raw),
                    "status":"ALREADY_IDENTICAL", "versioned":True}
        try:
            response = self.s3.put_object(
                Bucket=self.bucket, Key=key, Body=raw,
                ContentType="application/json", IfNoneMatch="*",
                Metadata={"sha256":digest(raw),"kind":"epoch2"})
        except Exception as exc:
            if error_code(exc) in ("412", "PreconditionFailed",
                                   "409", "ConditionalRequestConflict"):
                raced = self.read(key)
                require(raced is not None and raced.raw == raw,
                        "RACING_NONIDENTICAL_WRITE")
                return {"key":key, "sha256":digest(raw),
                        "status":"RACE_IDENTICAL", "versioned":True}
            raise EpochStorageBlocked("WRITE_FAIL_CLOSED:" + error_code(exc)) from exc
        version = response.get("VersionId")
        require(isinstance(version, str) and version not in ("", "null"),
                "UNVERSIONED_WRITE_STOP")
        verified = self.read(key)
        require(verified is not None and verified.version == version and
                verified.raw == raw, "POSTWRITE_VERIFICATION_FAILED")
        return {"key":key, "sha256":digest(raw),
                "status":"CREATED", "versioned":True}

    def create_genesis(self, policy_result: dict) -> dict:
        require(isinstance(policy_result, dict) and
                policy_result.get("status") ==
                "OFFLINE_EPOCH2_CANDIDATE_POLICY_PASS_NOT_AWS_ACCEPTANCE" and
                policy_result.get("new_epoch_genesis_committed") is False and
                policy_result.get("aws_mutations") is False and
                policy_result.get("broker_orders") is False and
                policy_result.get("paper_backfill") is False,
                "INVALID_OFFLINE_INCEPTION")
        manifest = policy_result.get("candidate_manifest")
        require(isinstance(manifest, dict) and
                policy_result.get("candidate_manifest_sha256") == epoch.sha(manifest) and
                manifest.get("book") == epoch.NEW_BOOK and
                manifest.get("new_prefix") == PREFIX and
                manifest.get("old_book") == epoch.OLD_BOOK and
                manifest.get("first_session") == epoch.FIRST_NEW_DAY and
                manifest.get("recorded_gaps") == list(epoch.MISSED) and
                manifest.get("old_nav_transferred") is False and
                manifest.get("performance_epoch_reset") is True and
                manifest.get("broker_actions_authorized") is False and
                manifest.get("original_book_anchors") == epoch.HISTORIC_SHA256,
                "INCORRECT_OR_MUTATED_GENESIS_MANIFEST")
        return self._create(GENESIS,{
            "schema":"stocklens-epoch2-genesis-v1",
            "book":epoch.NEW_BOOK,
            "manifest":manifest,
            "manifest_sha256":epoch.sha(manifest),
            "old_book_preserved":True,
            "independent_economic_nav_verified_by_storage":False,
            "broker_orders":False,
        })

    def record_missing_history(self) -> dict:
        genesis = self.read(GENESIS)
        require(genesis is not None and genesis.record.get("book")==epoch.NEW_BOOK,
                "GENESIS_REQUIRED_FOR_GAP_AUDIT")
        return self._create(GAPS,{
            "schema":"stocklens-epoch2-gap-event-v1",
            "book":epoch.NEW_BOOK,
            "old_book":epoch.OLD_BOOK,
            "status":"MISSED_UNRECOVERABLE_NO_BACKFILL",
            "missed_sessions":list(epoch.MISSED),
            "old_receipt_keys_unchanged":True,
            "original_anchor_sha256":epoch.HISTORIC_SHA256,
            "new_genesis_sha256":genesis.sha256,
            "broker_orders":False,
        })

    @staticmethod
    def session_key(day: str) -> str:
        require(isinstance(day, str) and DAY.fullmatch(day) is not None,
                "INVALID_SESSION_DATE")
        return PREFIX + "sessions/" + day + ".json"

    @staticmethod
    def continuity_key(day: str) -> str:
        require(isinstance(day, str) and DAY.fullmatch(day) is not None,
                "INVALID_SESSION_DATE")
        return PREFIX + "continuity/" + day + ".json"

    def commit_modeled_session(self, paper: dict, *,
                               next_exchange_session: Callable[[str], str],
                               independent_engine_verified: bool = False) -> dict:
        """Only storage linkage; private adapter must attest real model+quotes."""
        require(independent_engine_verified is True,
                "PRIVATE_ENGINE_INDEPENDENT_PROOF_MISSING")
        require(isinstance(paper, dict) and
                paper.get("book")==epoch.NEW_BOOK and
                paper.get("mode")=="SHADOW_ONLY_NO_BROKER_ACTIONS" and
                paper.get("status")=="MODELED_FORWARD_SESSION_CANDIDATE" and
                paper.get("paper_backfill") is False and
                paper.get("broker_orders_authorized") is False and
                paper.get("broker_fills_observed") is False,
                "NOT_A_PROSPECTIVE_PAPER_RECEIPT")
        day = paper.get("session")
        self.session_key(day)
        require(day >= epoch.FIRST_NEW_DAY and day not in epoch.MISSED,
                "HISTORICAL_PAPER_REPLAY_FORBIDDEN")
        genesis = self.read(GENESIS)
        gaps = self.read(GAPS)
        require(genesis is not None and gaps is not None and
                gaps.record.get("new_genesis_sha256")==genesis.sha256,
                "GENESIS_OR_MISSED_EVENT_MISSING")
        previous = paper.get("prior_session")
        if day == epoch.FIRST_NEW_DAY:
            require(previous == epoch.PREVIOUS_SIGNAL_DAY,
                    "WRONG_FIRST_EPOCH2_PRIOR_SESSION")
            prior_sha = genesis.sha256
            prior_continuity = None
        else:
            require(isinstance(previous,str) and DAY.fullmatch(previous) and
                    previous >= epoch.FIRST_NEW_DAY and
                    callable(next_exchange_session) and
                    next_exchange_session(previous) == day,
                    "MARKET_SESSION_CHAIN_GAP")
            prior_paper = self.read(self.session_key(previous))
            prior_continuity = self.read(self.continuity_key(previous))
            require(prior_paper is not None and prior_continuity is not None and
                    prior_continuity.record.get("paper_sha256")==prior_paper.sha256 and
                    prior_continuity.record.get("paper_version_id")==prior_paper.version and
                    prior_continuity.record.get("status")=="STRUCTURAL_ONLY_NOT_ECONOMICALLY_QUALIFIED",
                    "PREVIOUS_PAPER_CONTINUITY_UNQUALIFIED")
            prior_sha = prior_paper.sha256
        require(paper.get("previous_receipt_sha256")==prior_sha and
                paper.get("genesis_sha256")==genesis.sha256 and
                isinstance(paper.get("state"),dict) and
                paper["state"].get("last_mark_session")==day,
                "MODEL_RECEIPT_STATE_OR_SHA_MISMATCH")
        pkey = self.session_key(day)
        p = self._create(pkey,paper)
        current = self.read(pkey)
        require(current is not None and current.sha256 == p["sha256"],
                "PAPER_WRITE_INCOMPLETE")
        continuity = {
            "schema":"stocklens-epoch2-continuity-v1",
            "book":epoch.NEW_BOOK,"session":day,"status":"STRUCTURAL_ONLY_NOT_ECONOMICALLY_QUALIFIED",
            "paper_key":pkey,"paper_sha256":current.sha256,
            "paper_version_id":current.version,
            "genesis_sha256":genesis.sha256,
            "previous_record_sha256":(
                prior_continuity.sha256 if prior_continuity else genesis.sha256),
            "broker_orders":False,"broker_fills":False,
            "old_epoch_alarm_preserved":True,
            "economic_NAV_attested_by_storage":False,
        }
        c = self._create(self.continuity_key(day),continuity)
        verified = self.read(self.continuity_key(day))
        require(verified is not None and verified.sha256 == c["sha256"] and
                verified.record["paper_sha256"]==current.sha256 and
                verified.record["paper_version_id"]==current.version,
                "CONTINUITY_NOT_VERIFIED")
        return {"status":"EPOCH2_STORAGE_LINKED_NOT_ECONOMIC_ACCEPTANCE",
                "session":day,"paper_sha256":current.sha256,
                "continuity_sha256":verified.sha256,
                "versions_present":True,"old_epoch_alarm_preserved":True,
                "broker_orders":False}

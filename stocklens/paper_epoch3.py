"""Pure, NON-DEPLOYABLE contract for an isolated ST Paper recovery epoch.

Old book, gaps and historic alerts are immutable evidence. New epoch is disjoint,
never silently relabels historical gaps as Paper fills, and has a new NAV
inception rather than carrying unverified wealth across a broken chain.

This module only validates supplied attestation inputs and returns a DRAFT.
It does not fetch live market data, emit an S3 write, call AWS or a broker.
No result from this module alone certifies that a Lambda implementation or
the actual live Watchdog follows this policy.
"""
from __future__ import annotations

from datetime import date, datetime, timezone, time, timedelta
import hashlib
import json
import math
import re
from zoneinfo import ZoneInfo

class EpochPolicyError(ValueError):
    pass


OLD_BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK"
NEW_BOOK = "NEW_AWS_INDEPENDENT_STAGING_BOOK_EPOCH3_20261112"
NEW_PREFIX = "paper/epochs/" + NEW_BOOK + "/"
LAST_OLD_DAY = "2026-11-04"
MISSED = ("2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11")
FIRST_NEW_DAY = "2026-11-12"
PREVIOUS_SIGNAL_DAY = "2026-11-11"

# Original historic SHA pins from prior read-only S3 evidence; this module does not reverify AWS.
HISTORIC_SHA256 = {
    "paper/book/" + OLD_BOOK + "/genesis.json":
        "355398c0e93b9ea0aeb17f71fb90e4f040156314bff6eaf4fba3f3297c8cd8e1",
    "paper/sessions/2026-11-04.json":
        "797bccafa9aba7b3799c312bbd1ed2f67e0101c127f2bcbdec6318d91f2f22d2",
    "paper/continuity/2026-11-04.json":
        "92d39a078d1859b0f1870826b89eb093d610dcb279696b778ce4b8d709db6eae",
}

# Narrow one-off date proof, NOT a general US holiday calendar.
# NYSE official 2026 schedule: https://www.nyse.com/trade/hours-calendars
# When expanded to other dates, the caller MUST provide an actual XNYS calendar.
PINNED_XNYS_SUCCESSION = (PREVIOUS_SIGNAL_DAY, FIRST_NEW_DAY)
UTC = timezone.utc
NY = ZoneInfo("America/New_York")


def ensure(ok: bool, error: str) -> None:
    if not ok:
        raise EpochPolicyError(error)


def read_utc(value: str) -> datetime:
    ensure(isinstance(value, str) and value.endswith("Z"),
           "INVALID_UTC_TIMESTAMP")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError) as exc:
        raise EpochPolicyError("INVALID_UTC_TIMESTAMP") from exc
    ensure(dt.utcoffset() == timedelta(0),
           "NON_UTC_TIMESTAMP")
    return dt.astimezone(UTC)


def sha(obj: dict) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=True).encode("utf-8")).hexdigest()


def old_epoch_attested(proposal: dict) -> dict:
    """Only structure, cryptographic anchor pins and explicit missing days."""
    ensure(isinstance(proposal, dict) and
           proposal.get("status") ==
           "FORWARD_ONLY_EPOCH_RECOVERY_PROPOSAL_NOT_DEPLOYABLE",
           "NOT_VETTED_READ_ONLY_PLAN")
    ensure(proposal.get("deployment_authorized") is False and
           proposal.get("aws_mutations") is False and
           proposal.get("broker_orders") is False and
           proposal.get("new_genesis_written") is False and
           proposal.get("paper_replayed") is False and
           proposal.get("old_book_mutated") is False,
           "PLAN_HAS_EFFECTS_OR_WRONG_PERMISSIONS")
    older = proposal.get("old_epoch") or {}
    ensure(older.get("book_id") == OLD_BOOK and
           older.get("last_qualified_session") == LAST_OLD_DAY and
           older.get("genesis_and_links") == "ALL_MATCH" and
           older.get("archived_immutable_anchor_sha256") == HISTORIC_SHA256 and
           older.get("state") == "BREACHED_AND_PRESERVED_UNCHANGED" and
           older.get("historical_alarm_truth") == "PRESERVE_HISTORIC_FAIL_CLOSED",
           "OLD_BOOK_OR_ARCHIVE_ANCHORS_NOT_VERIFIED")
    gaps = proposal.get("unqualified_sessions")
    ensure(isinstance(gaps, list) and len(gaps) == len(MISSED) and
           [x.get("session") for x in gaps] == list(MISSED), "GAP_DAYS_DIFFER")
    for gap in gaps:
        ensure(gap.get("proposed_gap_status") ==
               "MISSED_UNRECOVERABLE_NO_BACKFILL" and
               gap.get("old_paper_receipt") ==
               "MISSING_AND_MUST_REMAIN_MISSING" and
               gap.get("old_continuity") ==
               "MISSING_AND_MUST_REMAIN_MISSING" and
               gap.get("broker_execution_claim") is False,
               "GAP_FALSIFICATION_RISK")
    target = proposal.get("new_epoch") or {}
    ensure(target.get("proposed_book_id") == NEW_BOOK and
           target.get("proposed_first_exchange_session") == FIRST_NEW_DAY and
           target.get("initial_NAV") == "NO_VALUE_ASSIGNED_OR_INFERRED" and
           target.get("ledger") ==
           "DISTINCT_NEW_S3_PREFIX_WITH_OWN_GENESIS_AND_CHAIN",
           "WRONG_NEW_EPOCH_TARGET")
    return {"old_book": OLD_BOOK, "new_book": NEW_BOOK,
            "last_attested": LAST_OLD_DAY,
            "missed": list(MISSED),
            "old_anchor_sha256": dict(HISTORIC_SHA256)}


def pinned_xnys_session() -> dict:
    """Prove ONLY Nov 11 -> Nov 12 with pinned official schedule context."""
    previous, next_day = PINNED_XNYS_SUCCESSION
    first = date.fromisoformat(next_day)
    previous_date = date.fromisoformat(previous)
    ensure(previous_date.weekday() == 2 and first.weekday() == 3 and
           (first - previous_date).days == 1,
           "UNEXPECTED_PINNED_XNYS_CALENDAR_INTERVAL")
    opening = datetime.combine(first, time(9, 30), NY).astimezone(UTC)
    closing = datetime.combine(first, time(16, 0), NY).astimezone(UTC)
    ensure(opening.isoformat() == "2026-11-12T14:30:00+00:00" and
           closing.isoformat() == "2026-11-12T21:00:00+00:00",
           "EXCHANGE_SESSION_DST_MISMATCH")
    return {
        "status":"PINNED_NYSE_NOV12_REGULAR_SESSION_2026_ONLY",
        "source":"https://www.nyse.com/trade/hours-calendars",
        "prior_exchange_session":previous,
        "new_exchange_session":next_day,
        "opening_utc":opening.isoformat().replace("+00:00","Z"),
        "closing_utc":closing.isoformat().replace("+00:00","Z"),
        "no_general_calendar_claim":True,
    }


def assess_bootstrap_candidate(
    proposal: dict,
    *,
    verified_prior_signal: dict,
    execution_market: dict,
    inception: dict,
    now_utc: str,
) -> dict:
    """Validate supplied evidence; never emit a signed Genesis or receipts.

    Inputs are operator/provider assertions, not trusted AWS read receipts.
    Any future adapter must reverify original objects, version IDs, funds,
    market data (actual 1m bars), CAs and timestamps independently.
    """
    old = old_epoch_attested(proposal)
    session = pinned_xnys_session()
    now = read_utc(now_utc)
    opening = read_utc(session["opening_utc"])
    closing = read_utc(session["closing_utc"])
    ensure(now > closing, "CANNOT_PREQUALIFY_FUTURE_PAPER_SESSION")

    ensure(isinstance(verified_prior_signal, dict) and
           verified_prior_signal.get("session") == PREVIOUS_SIGNAL_DAY and
           verified_prior_signal.get("mode") ==
           "SHADOW_ONLY_NO_BROKER_ACTIONS" and
           verified_prior_signal.get("broker_actions_enabled") is False and
           verified_prior_signal.get("version_id_present") is True and
           bool(re.fullmatch(r"[a-f0-9]{64}",
                             str(verified_prior_signal.get("sha256", "")))),
           "UNVERIFIED_PREVIOUS_SESSION_FROZEN_SIGNAL")
    archived = read_utc(verified_prior_signal.get("archived_at_utc", ""))
    # Prior decision must be saved after its actual Nov11 market close and
    # before Nov12 market open; otherwise the signal is stale/lookahead.
    prior_close = datetime(2026, 11, 11, 21, 0, tzinfo=UTC)
    ensure(prior_close <= archived < opening and archived < now,
           "LOOKAHEAD_OR_SAME_SESSION_SIGNAL")
    ensure(isinstance(execution_market, dict) and
           execution_market.get("session") == FIRST_NEW_DAY and
           execution_market.get("mode") == "CLOSED_REGULAR_XNYS" and
           execution_market.get("broker_orders_enabled") is False and
           execution_market.get("independent_vendor_close_verified") is True and
           execution_market.get("near_session_close_present") is True and
           execution_market.get("duplicate_bars_present") is False,
           "EXECUTION_SOURCE_NOT_QUALIFIED")
    bars = execution_market.get("minute_bars")
    ensure(isinstance(bars, dict) and set(bars) == {"QQQ","TQQQ"} and
           all(type(bars[s]) is int and 385 <= bars[s] <= 390
               for s in ("QQQ","TQQQ")),
           "NOT_ENOUGH_UNIQUE_MINUTE_BARS")
    ensure(isinstance(inception, dict) and
           inception.get("operator_approved") is True and
           inception.get("source") ==
           "NEW_INDEPENDENT_SIMULATED_CAPITAL_NO_OLD_NAV_TRANSFER" and
           inception.get("old_book_inherited") is False,
           "UNAPPROVED_OR_BRIDGED_NAV")
    balance = inception.get("starting_cash_usd")
    ensure(type(balance) in (int,float) and
           math.isfinite(balance) and balance > 0,
           "NO_VERIFIED_NEW_EPOCH_CAPITAL")
    ensure(inception.get("initial_shares") == {"QQQ":0,"TQQQ":0},
           "UNATTESTED_INHERITED_HOLDINGS")
    approved_at = read_utc(inception.get("approved_at_utc", ""))
    ensure(approved_at < opening and approved_at < now,
           "RETROACTIVE_INCEPTION_APPROVAL")
    manifest = {
        "schema":"stocklens-paper-epoch3-candidate-v1",
        "book":NEW_BOOK,"old_book":OLD_BOOK,
        "new_prefix":NEW_PREFIX,
        "first_session":FIRST_NEW_DAY,
        "prior_session_signal":PREVIOUS_SIGNAL_DAY,
        "original_book_anchors":old["old_anchor_sha256"],
        "old_book_last_qualified":LAST_OLD_DAY,
        "recorded_gaps":list(MISSED),
        "prior_signal_sha256":verified_prior_signal["sha256"],
        "starting_cash_usd":float(balance),
        "initial_shares":{"QQQ":0,"TQQQ":0},
        "old_nav_transferred":False,
        "performance_epoch_reset":True,
        "broker_actions_authorized":False,
        "market_minute_bar_counts":bars,
        "approval_prior_to_open":True,
        "signal_prior_to_open":True,
    }
    return {
        "status":"OFFLINE_EPOCH3_CANDIDATE_POLICY_PASS_NOT_AWS_ACCEPTANCE",
        "candidate_manifest_sha256":sha(manifest),
        "candidate_manifest":manifest,
        "prior_source_provenance_independently_verified":False,
        "new_epoch_genesis_committed":False,
        "new_epoch_paper_receipt_committed":False,
        "watchdog_green":False,
        "original_epoch_alarm_state":"PRESERVE_FAIL_CLOSED",
        "new_epoch_monitor_state":"NOT_STARTED_UNVERIFIED",
        "new_epoch_qualification":"NO_LIVE_PROSPECTIVE_EVIDENCE",
        "further_proof_required":[
            "AUTHENTICATED_AWS_READS_AND_IMMUTABLE_CONDITIONAL_PUTS",
            "AUDIT_NEW_GENESIS_RECEIPT_S3_VERSION_LINKS_AND_ECONOMIC_NAV",
            "MATCH_WATCHDOG_TO_NEW_EPOCH_ONLY_WITH_ORIGINAL_ALARMS_PRESERVED",
            "VALIDATE_VERIFIED_MARKET_BARS_AND_CORPORATE_ACTIONS",
            "ONE_REAL_FORWARD_PAPER_SESSION_AND_MULTI_SESSION_SOAK",
        ],
        "aws_mutations":False, "broker_orders":False, "paper_backfill":False,
    }


def monitor_partition(*, original_missing: bool, prospective_receipt_qualified: bool,
                      new_genesis_verified: bool) -> dict:
    """Old historical alarm must NEVER become OK through an epoch switch."""
    return {
        "original_epoch_status":("FAIL_CLOSED_HISTORIC_GAP"
                                 if original_missing else "UNKNOWN_NOT_ASSESSED"),
        "new_epoch_status":("INPUT_FLAGS_SAY_QUALIFIED_BUT_NOT_LIVE_ATTESTED"
                            if prospective_receipt_qualified and new_genesis_verified
                            else "NOT_QUALIFIED"),
        "cross_epoch_aggregate_nav_authorized":False,
        "can_manually_clear_old_alarm":False,
        "historical_missing_receipts_stay_missing":True,
        "real_watchdog_changed":False,
    }

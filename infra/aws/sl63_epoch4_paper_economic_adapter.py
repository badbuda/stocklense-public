"""Epoch4 *offline integration candidate*: economic BUY/SELL + immutable S3 pair.

Not a deployed Lambda, no handler entrypoint, no boto3 client, no scheduling,
no broker. This composes actual stocklens.paper model with the new versioned
Epoch4 store and explicit lag-1 exchange/session/approval constraints.

A passed synthetic test is NOT real-market or live AWS acceptance. The later
new runtime must independently attest vendor quotes, source provenance,
monitoring and a valid preopen-start timeline before any real ST invocation.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
import hashlib
import json

import exchange_calendars as xcals

from infra.aws import sl63_epoch4_immutable_store as store
from stocklens import paper as model


class Epoch4IntegrationBlocked(RuntimeError):
    pass


def require(ok, label):
    if not ok:
        raise Epoch4IntegrationBlocked(label)


def _time(value):
    if isinstance(value,str):
        value=datetime.fromisoformat(value.replace("Z","+00:00"))
    require(isinstance(value,datetime) and value.tzinfo is not None,
            "UTC_TIME_REQUIRED")
    return value.astimezone(timezone.utc)


def _verified(s3, key):
    """Read latest VERSIONED source bytes; refuse drift, deletion and truncation."""
    h=s3.head_object(Bucket=store.ST_BUCKET,Key=key)
    version=h.get("VersionId")
    require(isinstance(version,str) and bool(version) and version!="null",
            "SOURCE_VERSION_ID_MISSING")
    size=h.get("ContentLength")
    require(type(size) is int and 2<=size<=store.MAX_BYTES,
            "SOURCE_SIZE_INVALID")
    r=s3.get_object(Bucket=store.ST_BUCKET,Key=key,VersionId=version)
    require(r.get("VersionId")==version,"SOURCE_PINNED_VERSION_CHANGED")
    raw=r["Body"].read(store.MAX_BYTES+1)
    require(len(raw)==size,"SOURCE_BYTE_LENGTH_CHANGED")
    sha=hashlib.sha256(raw).hexdigest()
    metadata=(h.get("Metadata") or {}).get("sha256")
    if metadata is not None:
        require(metadata==sha,"SOURCE_STORED_SHA_MISMATCH")
    try:
        obj=json.loads(raw)
    except ValueError as exc:
        raise Epoch4IntegrationBlocked("SOURCE_JSON_INVALID") from exc
    require(type(obj) is dict,"SOURCE_NOT_OBJECT")
    return {"key":key,"version_id":version,"sha256":sha,"payload":obj,
            "saved_utc":_time(h["LastModified"])}


def _market_clock(session, now):
    cal=xcals.get_calendar("XNYS")
    require(cal.is_session(session),"NON_NYSE_EPOCH4_SESSION")
    prior=cal.previous_session(session).date().isoformat()
    opening=_time(cal.session_open(session).to_pydatetime())
    closing=_time(cal.session_close(session).to_pydatetime())
    prior_close=_time(cal.session_close(prior).to_pydatetime())
    require(_time(now)>closing,"UNCOMPLETED_MARKET_SESSION")
    return prior,prior_close,opening,closing


def _approval(s3, session, opening):
    approval=_verified(s3,store.PREFIX+"preopen-inception-approval.json")
    p=approval["payload"]
    require(p.get("schema")=="stocklens-epoch4-preopen-inception-intent-v1"
            and p.get("book")==store.EPOCH
            and p.get("first_session")=="2026-11-19"
            and p.get("starting_cash_usd")==100000.0
            and p.get("starting_shares")=={"QQQ":0,"TQQQ":0}
            and p.get("old_nav_transferred") is False
            and p.get("broker_orders_authorized") is False
            and p.get("mode")=="SHADOW_ONLY_NO_BROKER_ACTIONS",
            "EPOCH4_PREOPEN_APPROVAL_INVALID")
    require(approval["saved_utc"]<opening,
            "APPROVAL_NOT_SAVED_BEFORE_FIRST_OPEN")
    return approval


def _previous_state(s3, session, first):
    if session==first:
        return model.new_state(),None,None,True
    cal=xcals.get_calendar("XNYS")
    previous=cal.previous_session(session).date().isoformat()
    paper=_verified(s3,store.key_for("sessions",previous))
    continuity=_verified(s3,store.key_for("continuity",previous))
    pp,cp=paper["payload"],continuity["payload"]
    require(pp.get("book")==store.EPOCH and pp.get("session")==previous
            and pp.get("broker_orders_authorized") is False and
            pp.get("broker_fills_observed") is False,
            "PRIOR_PAPER_WRONG_BOOK_OR_BROKER_MODE")
    st=pp.get("state")
    require(type(st) is dict and st.get("last_mark_session")==previous,
            "PRIOR_STATE_NOT_MATCHING_COMPLETED_SESSION")
    ev=cp.get("evidence") or {}
    require(cp.get("book")==store.EPOCH and cp.get("session")==previous
            and cp.get("status")=="MODELLED_RECEIPT_NOT_INDEPENDENTLY_QUALIFIED"
            and cp.get("broker_orders") is False and cp.get("broker_fills") is False
            and ev.get("paper_sha256")==paper["sha256"]
            and ev.get("paper_version_id")==paper["version_id"]
            and ev.get("paper_key")==paper["key"],
            "PRIOR_CONTINUITY_MISSING_OR_NOT_PINNED")
    return deepcopy(st),paper,continuity,False


def _source_signal(s3, session, prior, prior_close, opening, approval):
    signal=_verified(s3,"signals/"+prior+".json")
    p=signal["payload"]
    require(p.get("mode")=="SHADOW_ONLY_NO_BROKER_ACTIONS"
            and p.get("execution_plan",{}).get("broker_actions_enabled") is False
            and p.get("latest",{}).get("asof_date")==prior,
            "LAG1_SIGNAL_NOT_FROZEN_OR_WRONG_SESSION")
    generated=_time(p.get("generated_at_utc"))
    require(prior_close<=generated<opening and
            prior_close<=signal["saved_utc"]<opening,
            "LAG1_SIGNAL_NOT_FROZEN_BEFORE_OPEN")
    if session=="2026-11-19":
        approved=approval["payload"]
        require(approved.get("prior_signal_key")==signal["key"]
                and approved.get("prior_signal_version_id")==signal["version_id"]
                and approved.get("prior_signal_sha256")==signal["sha256"],
                "INITIAL_SIGNAL_NOT_IDENTICAL_TO_PREOPEN_APPROVAL")
    return signal


def build_and_store_pair(s3, *, session, market, observed_at_utc):
    """Offline injectable S3 integration, NOT a deployable AWS handler.

    No raw historical sessions before approved 2026-11-19 are accepted.
    Missed prior exchanges are rejected: no backfill or synthetic continuity.
    The caller MUST supply point-in-time source-attested market data later;
    the current adapter cannot qualify its market bars by itself.
    """
    store.validate_session(session)
    prior,prior_close,opening,closing=_market_clock(session,observed_at_utc)
    require(market.session_date==session,"MARKET_SESSION_MISMATCH")
    # The market object is injected and does not prove actual vendor sourcing.
    require(isinstance(market,model.SessionMarket),
            "INJECTED_MARKET_DATA_CLASS_REQUIRED")
    approval=_approval(s3,"2026-11-19",
                       _market_clock("2026-11-19",
                                     "2026-11-20T23:00:00Z")[2])
    state,prev_paper,prev_continuity,bootstrap=_previous_state(
        s3,session,"2026-11-19")
    signal=_source_signal(s3,session,prior,prior_close,opening,approval)

    # Only the first approved simulated book may create its Genesis.
    # The Genesis record is deterministic for safe retry; it does not
    # transfer or heal the old interrupted book.
    if bootstrap:
        g={
            "book":store.EPOCH,"first_session":"2026-11-19",
            "starting_cash_usd":100000.0,"starting_shares":{"QQQ":0,"TQQQ":0},
            "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
            "broker_orders_authorized":False,
            "old_book_transferred":False,
            "approval_sha256":approval["sha256"],
            "approval_version_id":approval["version_id"],
            "initial_prior_signal_sha256":signal["sha256"],
            "initial_prior_signal_version_id":signal["version_id"],
        }
        genesis=store.put_once_or_identical(
            s3,key=store.key_for("genesis"),payload=g)
    else:
        # A new session must never silently manufacture missing Genesis.
        genesis=_verified(s3,store.key_for("genesis"))

    before=deepcopy(state)
    actions=model._apply_corporate_actions(state,market)
    trades=model.rebalance_if_required(state,signal["payload"],market,bootstrap)
    row=model.mark_session(state,signal["payload"],market,trades,actions,bootstrap)

    require(row["session_date"]==session
            and state["last_mark_session"]==session
            and all(int(state["shares"][x])>=0 for x in model.SYMBOLS)
            and float(state["cash"])>=-1e-7,
            "MODELLED_ACCOUNTING_INCONSISTENT")
    paper={
        "book":store.EPOCH,"session":session,
        "mode":"SHADOW_ONLY_NO_BROKER_ACTIONS",
        "broker_orders_authorized":False,"broker_fills_observed":False,
        "execution_evidence":"INJECTED_MARKET_NOT_INDEPENDENTLY_ATTESTED",
        "signal":{"key":signal["key"],"version_id":signal["version_id"],
                  "sha256":signal["sha256"]},
        "prior_paper_sha256":prev_paper["sha256"] if prev_paper else None,
        "prior_continuity_sha256":prev_continuity["sha256"]
                                 if prev_continuity else None,
        "start_state":before,"trades":trades,"row":row,"state":state,
    }
    def continuation(saved):
        return {
            "book":store.EPOCH,"session":session,
            "status":"MODELLED_RECEIPT_NOT_INDEPENDENTLY_QUALIFIED",
            "broker_orders":False,"broker_fills":False,
            "previous_record_sha256":(
                prev_continuity["sha256"] if prev_continuity else None),
            "evidence":{"paper_sha256":saved.sha256,
                        "paper_key":saved.key,
                        "paper_version_id":saved.version_id},
        }
    receipt=store.save_paper_and_continuity(
        s3,session=session,paper_payload=paper,
        continuation_builder=continuation)
    return {"status":"EPOCH4_MODELED_PAIR_WRITTEN_NOT_LIVE_ACCEPTANCE",
            "session":session,"trades":len(trades),
            "sides":sorted(set(t["side"] for t in trades)),
            "all_injected_quotes_not_independently_verified":True,
            "real_aws_lambda_deployed":False,
            "broker_orders":False,**receipt}

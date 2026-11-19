"""Forward-only ST Epoch4 modeled Paper + exact-version crash recovery.

The scheduled Lambda derives its exchange session solely from the real clock,
never from a user-provided event date. An already committed immutable Paper
receipt is recovered by finalizing only its missing Continuity: no quote
refetch, no re-execution of trades, no duplicate Paper versions.

Live quotes are validated by stocklens.paper's complete Yahoo 1-minute
session checks. Yahoo is ONE vendor, NOT independent price corroboration;
every receipt makes that limitation explicit. No broker APIs are ever used.
"""
from __future__ import annotations

from datetime import datetime,timedelta,timezone
import hashlib
import json
import math
from zoneinfo import ZoneInfo

import exchange_calendars as xcals

from infra.aws import sl63_epoch4_paper_economic_adapter as adapter
from infra.aws import sl63_epoch4_immutable_store as store
from stocklens import paper as model

NY=ZoneInfo("America/New_York")
FIRST="2026-11-19"
VENDOR="YFINANCE_1M_RAW"
SOURCE_SCHEMA="sl63-yahoo-single-vendor-1m-quote-evidence-v1"


class ProspectivePaperBlocked(RuntimeError):
    pass


def require(ok,why):
    if not ok:raise ProspectivePaperBlocked(why)


def session_from_clock(now):
    now=adapter._time(now)
    local=now.astimezone(NY).date().isoformat()
    cal=xcals.get_calendar("XNYS")
    if not cal.is_session(local):
        return None
    _,_,_,close=adapter._market_clock(local,now)
    # This limit prohibits processing a missing day later: no backfill.
    require(now>=close+timedelta(minutes=15),
            "EPOCH4_WAIT_UNTIL_MARKET_DATA_SETTLED")
    require(now<=close+timedelta(hours=5),
            "EPOCH4_PROSPECTIVE_WINDOW_EXPIRED_NO_BACKFILL")
    store.validate_session(local)
    return local


def _quote_payload(market):
    require(type(market) is model.SessionMarket
            and market.source==VENDOR,
            "EPOCH4_NOT_REAL_YFINANCE_1M_MARKET")
    quote={"session":market.session_date,"vendor":VENDOR,
           "prices_0931":market.prices_0931,
           "prices_0932":market.prices_0932,
           "closes":market.closes,
           "dividends":market.dividends,
           "split_ratios":market.split_ratios}
    require(all(set(getattr(market,key))==set(model.SYMBOLS)
                for key in ("prices_0931","prices_0932","closes",
                            "dividends","split_ratios")),
            "EPOCH4_MISSING_QUOTE_OR_ACTION_SYMBOL")
    for kind in ("prices_0931","prices_0932","closes"):
        require(all(math.isfinite(float(x)) and float(x)>0
                    for x in getattr(market,kind).values()),
                "EPOCH4_PRICE_NOT_FINITE_POSITIVE")
    for kind in ("dividends","split_ratios"):
        require(all(math.isfinite(float(x)) and float(x)>=0
                    for x in getattr(market,kind).values()),
                "EPOCH4_ACTION_NONFINITE_OR_NEGATIVE")
    raw=store.canonical(quote)
    return {
        "schema":SOURCE_SCHEMA,
        "single_vendor":VENDOR,
        "fully_covered_regular_session_by_model_fetch":True,
        "modeled_fill_bar_minutes_et":["09:31","09:32"],
        "quotes_and_actions_sha256":hashlib.sha256(raw).hexdigest(),
        "independent_second_vendor_verified":False,
        "broker_fill_verified":False,
        "synthetic_quotes":False,
    }


def _s3_missing(exc):
    return (getattr(exc,"response",{}) or {}).get("Error",{}).get("Code") in (
        "NoSuchKey","404","NotFound")


def _read_or_absent(s3,key):
    try:
        return adapter._verified(s3,key)
    except Exception as exc:
        if _s3_missing(exc):
            return None
        raise


def _check_prior(s3,session,now):
    prior,priorclose,opening,closing=adapter._market_clock(session,now)
    _,_,firstopening,_=adapter._market_clock(
        FIRST,"2026-11-20T23:00:00Z")
    approval=adapter._approval(s3,FIRST,firstopening)
    signal=adapter._source_signal(
        s3,session,prior,priorclose,opening,approval)
    state,prev_paper,prev_continuity,bootstrap=adapter._previous_state(
        s3,session,FIRST)
    return signal,prev_paper,prev_continuity,bootstrap


def resume_existing_paper_if_any(s3,session,now):
    """Recover only persisted, pinned verified Paper; NEVER recalculate trades."""
    paper=_read_or_absent(s3,store.key_for("sessions",session))
    if paper is None:
        return None
    signal,prev_paper,prev_continuity,bootstrap=_check_prior(s3,session,now)
    g=adapter._verified(s3,store.key_for("genesis"))
    require(g["payload"].get("book")==store.EPOCH and
            g["payload"].get("first_session")==FIRST and
            g["payload"].get("old_book_transferred") is False,
            "EPOCH4_GENESIS_MISSING_OR_UNTRUSTED")
    p=paper["payload"]
    require(p.get("book")==store.EPOCH and
            p.get("session")==session and
            p.get("mode")=="SHADOW_ONLY_NO_BROKER_ACTIONS" and
            p.get("broker_orders_authorized") is False and
            p.get("broker_fills_observed") is False and
            p.get("state",{}).get("last_mark_session")==session and
            p.get("row",{}).get("session_date")==session and
            type(p.get("trades")) is list,
            "EXISTING_PAPER_NOT_COMPLETE_MODELLED_SHADOW")
    pinned=p.get("signal") or {}
    require(pinned.get("key")==signal["key"] and
            pinned.get("version_id")==signal["version_id"] and
            pinned.get("sha256")==signal["sha256"],
            "EXISTING_PAPER_SIGNAL_SOURCE_DRIFT")
    require(p.get("prior_paper_sha256")==(
                prev_paper["sha256"] if prev_paper else None)
            and p.get("prior_continuity_sha256")==(
                prev_continuity["sha256"] if prev_continuity else None),
            "EXISTING_PAPER_PRIOR_CHAIN_DRIFT")
    ev=p.get("market_evidence") or {}
    require(ev.get("schema")==SOURCE_SCHEMA and
            ev.get("single_vendor")==VENDOR and
            ev.get("synthetic_quotes") is False and
            ev.get("independent_second_vendor_verified") is False and
            len(ev.get("quotes_and_actions_sha256",""))==64,
            "PAPER_VENDOR_EVIDENCE_UNVERIFIED")
    # This reference is deliberately deterministic and based on stored
    # Paper version/hash. A 500 after the Paper write cannot double-trade.
    cont={
        "book":store.EPOCH,"session":session,
        "status":"MODELLED_RECEIPT_NOT_INDEPENDENTLY_QUALIFIED",
        "broker_orders":False,"broker_fills":False,
        "previous_record_sha256":(
             prev_continuity["sha256"] if prev_continuity else None),
        "evidence":{"paper_sha256":paper["sha256"],
                    "paper_key":paper["key"],
                    "paper_version_id":paper["version_id"]},
    }
    store._continuity_shape(cont,session,store.VerifiedReceipt(
        key=paper["key"],version_id=paper["version_id"],
        sha256=paper["sha256"],byte_count=0,created=False))
    stored=store.put_once_or_identical(
        s3,key=store.key_for("continuity",session),payload=cont)
    return {
        "status":"EPOCH4_EXISTING_PAPER_CONTINUITY_VERIFIED_NO_TRADE_REPLAY",
        "book":store.EPOCH,"session":session,
        "paper_version_id":paper["version_id"],
        "paper_sha256":paper["sha256"],
        "continuity_version_id":stored.version_id,
        "continuity_sha256":stored.sha256,
        "continuity_created_now":stored.created,
        "economic_model_reexecuted":False,
        "new_paper_written":False,
        "independent_vendor_verified":False,
        "broker_orders":False,
    }


def run_current_session(s3,*,now,market_fetch=None):
    session=session_from_clock(now)
    if session is None:
        return {"status":"XNYS_CLOSED_NO_PAPER_WRITE","broker_orders":False}
    already=resume_existing_paper_if_any(s3,session,now)
    if already is not None:return already
    prior,_,_,_=adapter._market_clock(session,now)
    # Verify all immutable inputs BEFORE network calls or new writes.
    _check_prior(s3,session,now)
    fetch=market_fetch or model.fetch_execution_market
    market=fetch(prior,session)
    require(market.session_date==session,
            "EPOCH4_MODEL_FETCH_RETURNED_WRONG_SESSION")
    evidence=_quote_payload(market)
    result=adapter.build_and_store_pair(
        s3,session=session,market=market,observed_at_utc=now,
        market_evidence=evidence)
    return {**result,
            "source":"YFINANCE_1M_RAW_SINGLE_VENDOR_NOT_INDEPENDENTLY_ATTESTED",
            "broker_orders":False}

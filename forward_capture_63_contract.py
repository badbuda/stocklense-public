"""Fail-closed contract for NEW frozen StockLens 8.0 forward evidence.

This is an OFFLINE schema validator, not a deployed trusted clock, S3 Object
Lock, signed witness, actual NBBO feed or broker. Local hashes can be forged
and can never promote a row to independent receipt qualification by themselves.
"""
from __future__ import annotations
import hashlib
import json
import math
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PREREG = Path("research/predeclarations/SL9-024-FROZEN8-63-PILOT.json")
OUT = Path("research/results/sl9_024_forward_63_readiness.json")
ZERO = "0"*64
NY = ZoneInfo("America/New_York")


def canonical(obj):
    return json.dumps(obj, sort_keys=True, separators=(",",":"), ensure_ascii=False).encode()


def sha256(obj):
    return hashlib.sha256(canonical(obj)).hexdigest()


def _clock(raw):
    try:
        x = datetime.fromisoformat(raw.replace("Z","+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("FORWARD_TIMESTAMP_INVALID") from exc
    if x.tzinfo is None:
        raise ValueError("FORWARD_TIMESTAMP_NOT_TIMEZONE_AWARE")
    return x.astimezone(timezone.utc)


def check(records, prereg, *, expected_through=None):
    if not isinstance(prereg,dict) or prereg.get("schema_version")!=1 or prereg.get("candidate")!="StockLens 8.0 FROZEN" or prereg.get("no_synthetic_etf") is not True or prereg.get("external_attestor_proven") is not False:
        raise ValueError("FORWARD_PREREG_CONTRACT_INVALID")
    if prereg.get("deployment_status")!="NOT_DEPLOYED" or prereg.get("broker_order_execution_authorized") is not False:
        raise ValueError("FORWARD_DEPLOYMENT_OR_ORDER_CLAIM_UNTRUSTED")
    if prereg.get("frozen_core_git_blob_sha")!="258c6918ea10456754bcd26f782af77545a56b2b":
        raise ValueError("FORWARD_FROZEN_CORE_PIN_MISMATCH")
    if not isinstance(records,list):
        raise ValueError("FORWARD_LEDGER_MUST_BE_LIST")
    seen=[]
    prev=ZERO
    complete=missed=0
    for record in records:
        if not isinstance(record,dict) or record.get("schema_version")!=1:
            raise ValueError("FORWARD_RECORD_INVALID")
        day=record.get("session_date")
        try:parsed=date.fromisoformat(day)
        except (ValueError,TypeError) as exc:raise ValueError("FORWARD_SESSION_INVALID") from exc
        if parsed.isoformat()!=day or day<prereg["earliest_capture_session"] or (seen and day<=seen[-1]):
            raise ValueError("FORWARD_NONMONOTONE_OR_RETROACTIVE_SESSION")
        state=record.get("status")
        if state not in ("COMPLETE","MISSED"):
            raise ValueError("FORWARD_UNDECLARED_SESSION_STATUS")
        if record.get("prior_record_sha256")!=prev:
            raise ValueError("FORWARD_HASH_CHAIN_BROKEN")
        if any(record.get(k) is not False for k in ("broker_orders_authorized","broker_fills_observed","synthetic_etf_prices_used","independent_vendor_receipt_proven")):
            raise ValueError("FORWARD_UNSUPPORTED_EXTERNAL_EVIDENCE_CLAIM")
        recorded_at = _clock(record.get("recorded_at_utc"))
        if state=="COMPLETE":
            signal=record.get("signal")
            market=record.get("market")
            if not isinstance(signal,dict) or not isinstance(market,dict):
                raise ValueError("FORWARD_MISSING_REAL_ETF_OR_SIGNAL_SOURCE")
            if signal.get("core_git_blob_sha")!=prereg["frozen_core_git_blob_sha"] or signal.get("target_leverage") not in (0,1.25,2,3):
                raise ValueError("FORWARD_NOT_FROZEN8_SIGNAL")
            if signal.get("asof_date","")>=day:
                raise ValueError("FORWARD_SIGNAL_LOOKAHEAD")
            open_ny=datetime.combine(parsed,time(9,30),tzinfo=NY).astimezone(timezone.utc)
            generated_at = _clock(signal.get("created_at_utc"))
            if generated_at>recorded_at:
                raise ValueError("FORWARD_RECORD_PREDATES_SIGNAL")
            if generated_at>=open_ny:
                raise ValueError("FORWARD_SIGNAL_AFTER_MARKET_OPEN")
            if market.get("source_kind")!="OBSERVED_ACTUAL_QQQ_TQQQ_ETF" or market.get("synthetic_etf") is not False:
                raise ValueError("FORWARD_NOT_REAL_ETF_PRICE_PATH")
            sha_map=market.get("raw_response_sha256")
            if not isinstance(sha_map,dict) or set(sha_map)!={"QQQ","TQQQ"} or any(
                  not isinstance(v,str) or len(v)!=64 or any(c not in "0123456789abcdef" for c in v)
                  for v in sha_map.values()):
                raise ValueError("FORWARD_UNVERIFIABLE_MARKET_PAYLOAD")
            if type(record.get("nav_usd")) not in (int,float) or not math.isfinite(record["nav_usd"]) or record["nav_usd"]<=0:
                raise ValueError("FORWARD_NAV_INVALID")
            complete+=1
        else:
            if record.get("signal") is not None or record.get("nav_usd") is not None or record.get("market") is not None:
                raise ValueError("FORWARD_MISSED_SESSION_CANNOT_HAVE_FILL_OR_NAV")
            if not isinstance(record.get("miss_reason"),str) or not record["miss_reason"]:
                raise ValueError("FORWARD_MISSED_REASON_REQUIRED")
            missed+=1
        expected=sha256({k:v for k,v in record.items() if k!="record_sha256"})
        if record.get("record_sha256")!=expected:
            raise ValueError("FORWARD_RECORD_SHA_INVALID")
        seen.append(day)
        prev=expected
    if expected_through is not None:
        import exchange_calendars as xcals
        if seen and expected_through<seen[-1]:
            raise ValueError("FORWARD_EXPECTED_END_BEFORE_LAST_RECORD")
        first=prereg["earliest_capture_session"]
        if expected_through>=first:
            cal=xcals.get_calendar("XNYS")
            required=[str(x.date()) for x in cal.sessions_in_range(first,expected_through)]
            if seen!=required:
                raise ValueError("FORWARD_MISSING_OR_NON_EXCHANGE_SESSION_WITHOUT_MISSED")
    return {"schema_version":1,"status":"WAITING_EXTERNAL_IMMUTABLE_SERVER_RECEIPTS",
      "original_legacy_007_rows_counted":0,
      "locally_consistent_session_records":len(seen),
      "complete_modeled_etf_sessions":complete,"explicit_missed_sessions":missed,
      "independently_attested_forward_sessions":0,
      "external_receipt_service_deployed":False,
      "63_session_capture_gate_passed":False,
      "252_session_statistical_alpha_proof":False,
      "actual_broker_fills_observed":False,
      "capital_deployment_authorized":False,
      "frozen_core_git_blob_sha":prereg["frozen_core_git_blob_sha"],
      "local_hash_chain_tail":prev}


def build():
    p=json.loads(PREREG.read_text())
    result=check([],p)
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n")
    print("STOCKLENS_FROZEN8_FORWARD_CONTRACT="+json.dumps(result,sort_keys=True))
    return result


if __name__=="__main__":
    build()

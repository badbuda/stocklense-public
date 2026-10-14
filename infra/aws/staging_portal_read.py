"""Pure verifier for private AWS staging S3 read-side portal summaries.

No writes, broker, API permissions, or authentication logic here; route-level
Cognito JWT MUST be enforced by API Gateway. A GetObject returns immutable
object bytes + the S3 server LastModified/version metadata. These summaries
are NOT a replacement for independent full-chain Paper verification.
"""
import hashlib
import json
from datetime import date

MAX_BODY=2_000_000
AUDIT_PASS="PASS_MODELLED_PAPER_ACCOUNTING_NOT_BROKER_FILLS"

def verified_body(raw:bytes,version_id:str,saved_at_utc:str):
    if not version_id or version_id=="null" or not saved_at_utc:
        raise ValueError("UNVERSIONED_OR_UNTIMED_S3_RECEIPT")
    if len(raw)>MAX_BODY:
        raise ValueError("STAGING_RECEIPT_TOO_LARGE")
    return json.loads(raw),{
        "sha256":hashlib.sha256(raw).hexdigest(),
        "version_id":version_id,
        "saved_at_utc":saved_at_utc,
    }

def summarize(day:str, get):
    """get(key)->None or (decoded evidence dict, metadata dict)."""
    try:
        if date.fromisoformat(day).isoformat()!=day:
            raise ValueError("BAD_SESSION_DATE")
        sig=get("signals/"+day+".json")
        paper=get("paper/sessions/"+day+".json")
        continuity=get("paper/continuity/"+day+".json")
        if not sig and not paper and not continuity:
            return {"session_date":day,"status":"NO_STAGING_RECEIPT"}
        if not sig:
            raise ValueError("PAPER_WITHOUT_ARCHIVED_SIGNAL")
        s, sm=sig
        if (s.get("mode")!="SHADOW_ONLY_NO_BROKER_ACTIONS" or
            s.get("latest",{}).get("asof_date")!=day or
            s.get("execution_plan",{}).get("broker_actions_enabled") is not False):
            raise ValueError("INVALID_STAGED_FROZEN_SIGNAL")
        result={"session_date":day,"status":"SIGNAL_S3_VERSIONED",
                "signal":{"level":s["latest"].get("level"),
                          "target_leverage":s["latest"].get("target_leverage"),**sm}}
        if paper or continuity:
            if not paper or not continuity:
                raise ValueError("PAPER_OR_CONTINUITY_PARTIAL")
            p,pm=paper
            c,cm=continuity
            if (p.get("session")!=day or
                p.get("current_signal_sha256")!=sm["sha256"] or
                p.get("broker_orders_authorized") is not False or
                p.get("broker_fills_observed") is not False or
                p.get("production_replacement_authorized") is not False or
                p.get("integrity",{}).get("status")!=AUDIT_PASS or
                c.get("session")!=day or
                c.get("evidence",{}).get("paper_sha256")!=pm["sha256"]):
                raise ValueError("S3_PAPER_CONTINUITY_BINDING_INVALID")
            result["paper"]={"equity":p["row"].get("equity"),
                             "trade_count":len(p.get("trades",[])),
                             "continuity_status":c.get("status"),**pm}
            result["status"]="SIGNAL_PAPER_CONTINUITY_S3_SHA_BOUND"
        return result
    except (ValueError,TypeError,KeyError,json.JSONDecodeError):
        return {"session_date":day,"status":"INVALID_EVIDENCE","signal":None,"paper":None}

"""Fail-closed point-in-time breadth input audit. Standard library only.

Input JSON: sessions [{session, decision_at, members:[{symbol,member_from,member_to,
membership_known_at, close, price_known_at}]}]. Timestamps UTC ISO8601.
This is an INPUT QUALIFICATION gate, NOT a source of historical Nasdaq membership.
"""
import datetime as dt
import json
import sys
from pathlib import Path

def utc(s):
    x=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
    if x.tzinfo is None: raise ValueError("timezone_required")
    return x.astimezone(dt.timezone.utc)

def audit(payload):
    if payload.get("source_kind") != "observed_constituent_pit":
        return {"status":"BLOCKED","reason":"NOT_OBSERVED_PIT_MEMBERSHIP"}
    rows=payload.get("sessions",[])
    if not rows: return {"status":"BLOCKED","reason":"NO_SESSIONS"}
    seen=set()
    summary=[]
    try:
        for row in rows:
            day=dt.date.fromisoformat(row["session"])
            if day in seen: raise ValueError("DUPLICATE_SESSION")
            seen.add(day)
            decision=utc(row["decision_at"])
            if decision.date()!=day: raise ValueError("DECISION_DATE_MISMATCH")
            members=row["members"]
            if not members: raise ValueError("EMPTY_MEMBERS")
            symbols=set()
            for m in members:
                symbol=m["symbol"]
                if symbol in symbols: raise ValueError("DUPLICATE_SYMBOL")
                symbols.add(symbol)
                if utc(m["membership_known_at"])>decision: raise ValueError("FUTURE_MEMBERSHIP_DISCLOSURE")
                if utc(m["price_known_at"])>decision: raise ValueError("FUTURE_PRICE")
                if dt.date.fromisoformat(m["member_from"])>day: raise ValueError("FUTURE_MEMBER")
                if m.get("member_to") and dt.date.fromisoformat(m["member_to"])<=day:
                    raise ValueError("DELISTED_MEMBER")
                close=float(m["close"])
                if not (0<close<float("inf")): raise ValueError("INVALID_PRICE")
            summary.append({"session":str(day),"observed_count":len(symbols)})
    except (KeyError,TypeError,ValueError,OverflowError) as exc:
        return {"status":"BLOCKED","reason":str(exc)}
    return {"status":"INPUT_QUALIFIED_ONLY","sessions":len(rows),
            "counts":summary,"warning":"Not proof of complete Nasdaq-100 membership or vendor historical revisions; no backtest authorized."}

if __name__=="__main__":
    result=audit(json.loads(Path(sys.argv[1]).read_text()))
    print(json.dumps(result,indent=2))
    sys.exit(0 if result["status"]=="INPUT_QUALIFIED_ONLY" else 2)

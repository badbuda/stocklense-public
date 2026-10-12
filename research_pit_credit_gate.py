"""Offline PIT credit-vintage audit. Input: pinned envelope, not bare FRED API JSON.

Envelope: {"series_id":"BAMLH0A0HYM2","response":<raw FRED observations JSON>}.
A caller-supplied series ID and file hash do NOT certify vendor origin,
licensed history, time-of-day release, or tradability.
"""
from __future__ import annotations
from datetime import date
from hashlib import sha256
import json,math

SERIES="BAMLH0A0HYM2"
def day(v):
    if not isinstance(v,str):raise ValueError("date invalid")
    try:d=date.fromisoformat(v)
    except ValueError as e:raise ValueError("date invalid") from e
    if d.isoformat()!=v:raise ValueError("date noncanonical")
    return d

def fred(raw):
    if not isinstance(raw,bytes) or not raw or len(raw)>8*1024*1024:
        raise ValueError("file invalid")
    try:d=json.loads(raw.decode("utf-8"))
    except (UnicodeError,ValueError) as e:raise ValueError("invalid JSON") from e
    if not isinstance(d,dict) or d.get("series_id")!=SERIES:
        raise ValueError("series not pinned")
    # FRED's native response does not include series_id. Require an
    # explicit, auditable acquisition envelope rather than guessing.
    response=d.get("response")
    if not isinstance(response,dict):raise ValueError("invalid FRED response")
    rows=response.get("observations")
    if (not isinstance(rows,list) or not rows or
        type(response.get("count")) is not int or
        response.get("offset")!=0 or response["count"]!=len(rows)):
        raise ValueError("incomplete observations")
    seen=set();old=set();valid=set();revisions=set();missing=0
    for x in rows:
        if not isinstance(x,dict):raise ValueError("invalid observation row")
        ob=day(x.get("date"));start=day(x.get("realtime_start"));end=day(x.get("realtime_end"))
        if ob>start or start>end:raise ValueError("future observation or inverted vintage")
        key=(ob,start,end)
        if key in seen:raise ValueError("duplicate vintage")
        seen.add(key)
        if x.get("value")==".":missing+=1;continue
        value=x.get("value")
        if type(value) not in (str,float,int):raise ValueError("spread invalid")
        try:v=float(value)
        except (ValueError,OverflowError) as e:raise ValueError("spread invalid") from e
        if not math.isfinite(v) or not 0<=v<=100:raise ValueError("spread invalid")
        valid.add(ob);revisions.add(start)
        if ob.year<=2022 and start.year<=2022:old.add(ob)
    return {
        "kind":"ICE_CREDIT_VINTAGE",
        "status":"BLOCKED_LICENSE_AND_RELEASE_CLOCK",
        "raw_sha256":sha256(raw).hexdigest(),
        "rows":len(rows),"missing_value_rows":missing,
        "unique_observations":len(valid),"distinct_vintage_starts":len(revisions),
        "pre2023_observations_with_pre2023_vintage":len(old),
        "pinned_envelope_is_independent_origin_proof":False,
        "release_time_certified":False,"licensed_h1_test":False,
        "independent_first_seen":False,"qualified_market_evidence":False,
        "synthetic_tqqq":False,"broker_orders_authorized":False,
        "frozen_stocklens8_changed":False,"capital_authorized":False,
    }

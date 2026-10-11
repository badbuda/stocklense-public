"""Offline PIT data audit. This parser cannot attest provider delivery or live fills."""
from __future__ import annotations
from datetime import date,datetime,timezone
from hashlib import sha256
import json,math,re
HEX=re.compile("^[0-9a-f]{64}$")
def utc(v):
    if not isinstance(v,str):raise ValueError("time missing")
    try:d=datetime.fromisoformat(v.replace("Z","+00:00"))
    except ValueError as e:raise ValueError("time invalid") from e
    if d.tzinfo is None:raise ValueError("time naive")
    return d.astimezone(timezone.utc)
def day(v):
    if not isinstance(v,str):raise ValueError("date invalid")
    try:d=date.fromisoformat(v)
    except ValueError as e:raise ValueError("date invalid") from e
    if d.isoformat()!=v:raise ValueError("date noncanonical")
    return d
def parse(raw):
    if not isinstance(raw,bytes) or len(raw)>8*1024*1024 or not raw:
        raise ValueError("file invalid")
    return json.loads(raw.decode("utf-8"))
def base(raw,kind):
    return dict(kind=kind,raw_sha256=sha256(raw).hexdigest(),
                independent_first_seen=False,qualified_market_evidence=False,
                synthetic_tqqq=False,broker_orders_authorized=False,
                frozen_stocklens8_changed=False,capital_authorized=False)
def fred(raw):
    d=parse(raw)
    if d.get("series_id")!="BAMLH0A0HYM2":raise ValueError("series not pinned")
    rows=d.get("observations")
    if not isinstance(rows,list) or not rows or d.get("offset")!=0 or d.get("count")!=len(rows):
        raise ValueError("incomplete observations")
    seen=set();old=set();valid=set();revisions=set()
    for x in rows:
        ob=day(x.get("date"));start=day(x.get("realtime_start"));end=day(x.get("realtime_end"))
        if ob>start or start>end:raise ValueError("future observation or inverted vintage")
        key=(ob,start,end)
        if key in seen:raise ValueError("duplicate vintage")
        seen.add(key)
        if x.get("value")==".":continue
        try:v=float(x["value"])
        except (ValueError,TypeError,KeyError) as e:raise ValueError("spread invalid") from e
        if not math.isfinite(v) or not 0<=v<=100:raise ValueError("spread invalid")
        valid.add(ob);revisions.add(start)
        if ob.year<=2022 and start.year<=2022:old.add(ob)
    z=base(raw,"ICE_CREDIT_VINTAGE")
    z.update(status="BLOCKED_LICENSE_AND_RELEASE_CLOCK",rows=len(rows),
             unique_observations=len(valid),distinct_vintage_starts=len(revisions),
             pre2023_observations_with_pre2023_vintage=len(old),
             release_time_certified=False,licensed_h1_test=False)
    return z

from __future__ import annotations
from datetime import date,datetime,time,timezone,timedelta
from zoneinfo import ZoneInfo
from market_calendar import calendar

NY=ZoneInfo("America/New_York")

def next_xnys_session(after_session:str)->str:
 cal=calendar()
 d=date.fromisoformat(after_session)
 # Search far enough to cross weekends and exchange holidays; fail closed otherwise.
 for n in range(1,15):
  candidate=(d+timedelta(days=n)).isoformat()
  if cal.is_session(candidate):
   return candidate
 raise RuntimeError("NO_NEXT_XNYS_SESSION_WITHIN_14_DAYS")

def execution_window(session:str,side:str)->dict:
 if not calendar().is_session(session):
  raise ValueError("NOT_XNYS_SESSION:"+session)
 side=side.upper()
 if side not in ("SELL","BUY"):
  raise ValueError("INVALID_SIDE:"+side)
 d=date.fromisoformat(session)
 t=time(9,31,0,0) if side=="SELL" else time(9,32,0,0)
 local=datetime.combine(d,t,tzinfo=NY);utc=local.astimezone(timezone.utc)
 return {"session":session,"side":side,"time_et":local.isoformat(),"time_utc":utc.isoformat(),"market_timezone":"America/New_York","calendar":"XNYS"}

def readiness(now_utc:datetime,session:str,side:str,signal_generated_utc:str)->dict:
 w=execution_window(session,side);target=datetime.fromisoformat(w["time_utc"]);signal=datetime.fromisoformat(signal_generated_utc.replace("Z","+00:00"))
 if now_utc.tzinfo is None:raise ValueError("NAIVE_NOW")
 if signal>=target:return {"status":"BLOCKED_LATE_SIGNAL",**w}
 delta=(target-now_utc.astimezone(timezone.utc)).total_seconds()
 status="UPCOMING" if delta>0 else ("EXECUTION_WINDOW" if delta>=-300 else "MISSED_WINDOW")
 return {"status":status,"seconds_to_window":int(delta),**w}

def readiness_by_side(now_utc:datetime,session:str,sides:list[str],signal_generated_utc:str)->dict:
 ordered=[s for s in ("SELL","BUY") if s in {x.upper() for x in sides}]
 return {s.lower():readiness(now_utc,session,s,signal_generated_utc) for s in ordered}

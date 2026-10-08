from __future__ import annotations
from datetime import datetime, timezone, timedelta, time
from zoneinfo import ZoneInfo
import exchange_calendars as xcals

CALENDAR="XNYS"
NY_TZ=ZoneInfo("America/New_York")
DAILY_BAR_SAFE_AFTER_NY=time(18,0)

def calendar():
 return xcals.get_calendar(CALENDAR)

def require_aware(now_utc):
 if now_utc.tzinfo is None: raise ValueError("now_utc must be timezone-aware")
 return now_utc.astimezone(timezone.utc)

def completed_sessions(now_utc=None,lookback_days=370,start_date=None):
 now=require_aware(now_utc or datetime.now(timezone.utc))
 cal=calendar()
 start=start_date or (now-timedelta(days=lookback_days)).date().isoformat()
 sessions=cal.sessions_in_range(start,now.date().isoformat())
 return [s for s in sessions if cal.session_close(s).to_pydatetime().astimezone(timezone.utc)<=now]

def latest_completed_session(now_utc=None,lookback_days=30):
 sessions=completed_sessions(now_utc,lookback_days)
 if not sessions: raise RuntimeError("NO_COMPLETED_XNYS_SESSION_IN_LOOKBACK")
 return sessions[-1]

def latest_completed_contract(now_utc=None):
 cal=calendar();s=latest_completed_session(now_utc)
 return {"session":s.date().isoformat(),"close_utc":cal.session_close(s).to_pydatetime().astimezone(timezone.utc).isoformat(),"calendar":CALENDAR,"source":"exchange_calendars"}


def latest_provider_eligible_contract(now_utc=None):
 now=require_aware(now_utc or datetime.now(timezone.utc))
 exchange=latest_completed_contract(now)
 now_ny=now.astimezone(NY_TZ)
 cal=calendar()
 latest=latest_completed_session(now)
 latest_date=latest.date()
 # The daily loader intentionally rejects a same-day bar until 18:00 New York.
 # Before that boundary, the prior XNYS session is the newest session the provider
 # contract permits us to publish as completed daily evidence.
 if latest_date==now_ny.date() and now_ny.time()<DAILY_BAR_SAFE_AFTER_NY:
  sessions=completed_sessions(now,lookback_days=30)
  if len(sessions)<2: raise RuntimeError("NO_PRIOR_PROVIDER_ELIGIBLE_XNYS_SESSION")
  eligible=sessions[-2]
  phase="WAITING_FOR_DAILY_BAR_SAFE_AFTER"
 else:
  eligible=latest
  phase="PROVIDER_DAILY_BAR_ELIGIBLE"
 return {
  "session":eligible.date().isoformat(),
  "exchange_latest_completed_session":exchange["session"],
  "exchange_latest_completed_close_utc":exchange["close_utc"],
  "safe_after_ny_time":DAILY_BAR_SAFE_AFTER_NY.strftime("%H:%M"),
  "now_ny":now_ny.isoformat(),
  "phase":phase,
  "calendar":CALENDAR,
  "source":"exchange_calendars+stocklens_daily_bar_safety_contract",
 }

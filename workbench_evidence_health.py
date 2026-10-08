from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import exchange_calendars as xcals
from market_calendar import latest_completed_contract,latest_provider_eligible_contract

def load(p):
 return json.loads(Path(p).read_text())

def _latest_completed_xnys_session(now_utc=None):
 return latest_completed_contract(now_utc)["session"]

def _session_contract(now_utc=None):
 data=load("docs/data.json")
 signal=data.get("signal",{})
 replay=load("docs/workbench.json").get("replay",{})
 signal_asof=signal.get("asof_date")
 replay_end=replay.get("end")
 latest_contract=latest_completed_contract(now_utc)
 provider_contract=latest_provider_eligible_contract(now_utc)
 latest_completed=latest_contract["session"]
 latest_completed_close=latest_contract["close_utc"]
 provider_eligible=provider_contract["session"]
 cal=xcals.get_calendar("XNYS")
 valid_session=False
 if signal_asof:
  try: valid_session=bool(cal.is_session(signal_asof))
  except Exception: valid_session=False
 future_session=bool(valid_session and signal_asof>latest_completed)
 latest=bool(valid_session and signal_asof==latest_completed)
 provider_current=bool(valid_session and signal_asof==provider_eligible)
 sessions_behind=None
 if valid_session and not future_session:
  try:
   cal_sessions=cal.sessions_in_range(signal_asof,latest_completed)
   sessions_behind=max(0,len(cal_sessions)-1)
  except Exception:
   sessions_behind=None
 if not valid_session: status="INVALID_XNYS_SESSION"
 elif future_session: status="FUTURE_SESSION"
 elif latest: status="LATEST_COMPLETED_SESSION"
 elif provider_current and provider_contract["phase"]=="WAITING_FOR_DAILY_BAR_SAFE_AFTER": status="WAITING_FOR_DAILY_BAR_SAFE_AFTER"
 elif sessions_behind==1: status="PROVIDER_LAG_AFTER_COMPLETED_CLOSE"
 else: status="ALIGNED_BUT_NOT_LATEST_COMPLETED_SESSION"
 return {
  "signal_asof":signal_asof,
  "replay_end":replay_end,
  "latest_completed_xnys_session":latest_completed,
  "latest_completed_close_utc":latest_completed_close,
  "provider_eligible_xnys_session":provider_eligible,
  "provider_phase":provider_contract["phase"],
  "daily_bar_safe_after_ny_time":provider_contract["safe_after_ny_time"],
  "status":status,
  "signal_replay_aligned":bool(signal_asof and replay_end and signal_asof==replay_end),
  "replay_role":"FROZEN_HISTORICAL_CONTEXT_NOT_LIVE_FRESHNESS_CLOCK",
  "valid_xnys_session":valid_session,
  "future_session":future_session,
  "latest_completed_session_match":latest,
  "provider_eligible_session_match":provider_current,
  "sessions_behind_latest_completed":sessions_behind,
  "calendar":"XNYS",
  "calendar_source":"exchange_calendars",
  "semantics":"LIVE_SIGNAL_VS_EXCHANGE_CALENDAR_COMPLETED_SESSION_FRESHNESS",
  "wall_clock_market_freshness_claimed":False,
  "provider_lag_detected":bool(valid_session and not future_session and not provider_current and sessions_behind is not None and sessions_behind>0),
  "note":"Exchange completion and provider-safe daily-bar eligibility are both exposed. Before 18:00 New York the loader intentionally permits only the prior XNYS daily bar; after 18:00 the latest exchange-completed session is required."
 }

def build(out="docs/workbench_evidence_health.json",now_utc=None):
 s=load("docs/workbench_selfcheck.json");m=load("docs/workbench_evidence_manifest.json");b=load("docs/workbench_evidence_bundle.json")
 if m.get("schema_version")!=1: raise RuntimeError("UNSUPPORTED_MANIFEST_SCHEMA")
 if b.get("schema_version")!=1: raise RuntimeError("UNSUPPORTED_BUNDLE_SCHEMA")
 if b.get("kind")!="STOCKLENS_WORKBENCH_CANONICAL_EVIDENCE_BUNDLE": raise RuntimeError("INVALID_BUNDLE_KIND")
 same=b.get("evidence_manifest",{}).get("manifest_sha256")==m.get("manifest_sha256")==s.get("manifest_sha256")
 session=_session_contract(now_utc)
 core_ok=s.get("status")=="PASS" and same and session["valid_xnys_session"] and not session["future_session"]
 d={"schema_version":1,"generated_at_utc":datetime.now(timezone.utc).isoformat(),"freshness":{"max_age_minutes":180,"semantics":"PUBLICATION_AGE_ONLY_NOT_MARKET_DATA_AGE"},"market_session":session,"kind":"WORKBENCH_EVIDENCE_HEALTH","status":"HEALTHY" if core_ok else "BLOCKED","market_session_freshness":"CURRENT" if session["provider_eligible_session_match"] else "STALE_SESSION","self_check":s.get("status"),"bundle_manifest_match":same,"manifest_sha256":m.get("manifest_sha256"),"replay_sessions":s.get("replay_sessions"),"transition_count":s.get("transition_count"),"evidence_classes":m.get("evidence_classes"),"full_lean_execution_parity":False,"automatic_model_change":False,"automatic_promotion":False}
 Path(out).write_text(json.dumps(d,indent=2)+"\n")
 if d["status"]!="HEALTHY":raise SystemExit("Workbench evidence health blocked: "+json.dumps({"self_check":d["self_check"],"bundle_manifest_match":d["bundle_manifest_match"],"market_session":d["market_session"],"market_session_freshness":d["market_session_freshness"]},sort_keys=True))
 return d

if __name__=="__main__":
 print(json.dumps(build(),indent=2))

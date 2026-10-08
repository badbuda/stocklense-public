from __future__ import annotations
import json,os
from pathlib import Path
from datetime import datetime,timezone
from broker_adapter import BrokerMode
OUT=Path("shadow_history/automation_guard.json")
def build(out=OUT):
 def j(p):
  q=Path(p);return json.loads(q.read_text()) if q.exists() else {}
 plan=j("shadow_history/execution_plan.json");ready=j("shadow_history/execution_readiness.json");policy=j("shadow_history/execution_policy.json")
 requested=os.getenv("STOCKLENS_BROKER_MODE","PAPER").upper()
 try:mode=BrokerMode(requested)
 except ValueError:mode=BrokerMode.DISABLED
 live_flag=os.getenv("STOCKLENS_LIVE_TRADING_ENABLED","false").lower()=="true"
 checks={
  "execution_plan_ready":plan.get("status")=="PLAN_READY",
  "paper_pipeline_ready":ready.get("status")=="READY",
  "broker_mode_not_live":mode is not BrokerMode.LIVE,
  "live_flag_disabled":not live_flag,
  "broker_not_authorized":not bool(plan.get("broker_authorized",False)),
 }
 safe=all(checks.values())
 late_review=policy.get("status")=="HUMAN_REVIEW_REQUIRED"
 next_action=policy.get("next_action") if late_review else ("PAPER_RECONCILE_ONLY" if safe else "STOP_AND_REVIEW")
 result={"status":"SAFE_PAPER_AUTOMATION" if safe else "BLOCKED","generated_at_utc":datetime.now(timezone.utc).isoformat(),"broker_mode":mode.value,"live_trading_enabled":live_flag,"checks":checks,"execution_required":bool(plan.get("execution_required")),"signal_date":plan.get("signal_date"),"policy":plan.get("policy",{}),"execution_policy_status":policy.get("status","MISSING"),"next_action":next_action,"automatic_catchup":False,"claim_boundary":"Operational watchdog only. It cannot authorize live orders or chase missed windows."}
 Path(out).parent.mkdir(parents=True,exist_ok=True);Path(out).write_text(json.dumps(result,indent=2)+"\n")
 if not safe: raise SystemExit("AUTOMATION_GUARD_BLOCKED")
 return result
if __name__=="__main__":print(json.dumps(build(),indent=2))
